"""
FIXME: 
1. 长短期记忆保存

继续丰富记忆

定时挑选记忆清除和更新整合


2. 消息列表不能无限追加

3. checkpoints.db 内容会随历史对话无限增长，需要定期清理

"""
from nt import system
import os
import json
import operator
from datetime import datetime
from re import T
import uuid
from dotenv import load_dotenv, dotenv_values
from typing_extensions import TypedDict, Annotated, Literal

from langchain.chat_models import init_chat_model
from langchain.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from langgraph.graph import StateGraph, START, END

from IPython.display import Image, display
from tools import TAVILY_TOOLS, SERP_API_TOOLS, SERP_PAPER_FOUCSED_TOOLS, MYSQL_TOOLS
from memory import (
    _MEM_SHORT_PAPER, _MEM_SHORT_STORE, _MEM_LONG,
    _get_round_num,
    _save_tool_results, _save_short_memory, _save_long_memory,
    _cleanup_duplicate_sessions,
)
from verify import _count_consecutive_failures, _has_paper_content

load_dotenv()


all_tools_by_name = {tool.name: tool for tool in TAVILY_TOOLS + SERP_API_TOOLS + MYSQL_TOOLS}

AVAILABLE_MODELS = {
    "google_genai": [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash",
        "gemini-3.1-pro-preview",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
}


def _apply_env_overrides(overrides: dict) -> None:
    """Apply env key-value overrides to os.environ at runtime."""
    """只修改 os.environ（进程内存），从不写入 .env 文件。.env 仅在服务器启动时读取一次。"""
    for k, v in overrides.items():
        if v is not None:
            os.environ[k] = str(v)
            print(f"[env] Override: {k} = {'***' if 'KEY' in k or 'PASSWORD' in k else v}")


gemini_model = init_chat_model("google_genai:gemini-2.5-flash-lite")
deepseek_model = init_chat_model("deepseek:deepseek-v4-pro")

search_model = init_chat_model("deepseek:deepseek-chat").bind_tools(TAVILY_TOOLS)
paper_collect_model = init_chat_model("deepseek:deepseek-chat").bind_tools(SERP_PAPER_FOUCSED_TOOLS + TAVILY_TOOLS)
mysql_execute_model = init_chat_model("deepseek:deepseek-chat").bind_tools(MYSQL_TOOLS)

def update_active_models(selected_model: str | None = None, env_overrides: dict | None = None) -> None:
    """Update global models in-place without rebuilding the compiled agent graph."""
    global search_model, paper_collect_model, mysql_execute_model

    if env_overrides:
        _apply_env_overrides(env_overrides)

    if selected_model:
        print(f"[model] Updating active models to: {selected_model}")
        search_model = init_chat_model(selected_model).bind_tools(TAVILY_TOOLS)
        paper_collect_model = init_chat_model(selected_model).bind_tools(SERP_PAPER_FOUCSED_TOOLS + TAVILY_TOOLS)
        mysql_execute_model = init_chat_model(selected_model).bind_tools(MYSQL_TOOLS)
    else:
        print("[model] Reverting to default deepseek-chat models")
        search_model = init_chat_model("deepseek:deepseek-chat").bind_tools(TAVILY_TOOLS)
        paper_collect_model = init_chat_model("deepseek:deepseek-chat").bind_tools(SERP_PAPER_FOUCSED_TOOLS + TAVILY_TOOLS)
        mysql_execute_model = init_chat_model("deepseek:deepseek-chat").bind_tools(MYSQL_TOOLS)


class MessagesState(TypedDict):
    messages: Annotated[list, operator.add]   # 消息列表，LangGraph 的 状态归并策略（reducer）。每个节点返回的 messages 不会覆盖原来的状态，而是追加
    tool_results: list[str]   # 中间工具调用的结果
    step: str            # 标记当前步骤
    intent: str          # "general" | "literature_collection"
    session_id: str      # unique ID linking short-term and long-term memory (one per thread)
    turn_num: int        # turn counter within a session (increments each user message)


def tool_node(state: MessagesState) -> dict:
    """Calling the tools"""

    _step_labels = {
        "llm_chatting": "chat_llm",
        "paper_collecting": "collect_paper",
        "data_saving": "mysql_process",
    }
    result = []
    for index, tool_call in enumerate(state["messages"][-1].tool_calls):
        _caller = _step_labels.get(state.get("step", ""), "?")
        try:
            print(f"🔍 [{_caller}] Calling tool {index + 1}: {tool_call['name']} ...")
            
            tool = all_tools_by_name[tool_call["name"]]
            tool_results = tool.invoke(tool_call["args"])
            result.append(ToolMessage(content=tool_results, tool_call_id=tool_call["id"]))
        
        except Exception as e:
            print(f"❌ Error calling tools: {e}")
            result.append(ToolMessage(content="Search API is temporarily unavailable", tool_call_id=tool_call["id"]))

    return {
        "tool_results": result,
        "messages": result
    }


def classify_intent_node(state: MessagesState) -> dict:
    """Classify user intent: general task or literature collection task"""

    system_prompt = """
    You are a request classifier. Based on the user's message, determine which category it belongs to:

    - "literature_collection": The user wants to search, collect, organize, or survey academic papers / research literature.
    - "general": Any other task, including general questions, factual queries, coding, analysis, etc.

    Reply with ONLY one of the two category strings: literature_collection or general. No explanation.
    """
    
    # _cleanup_duplicate_sessions()

    print("\n🧭 [classify intent] Classifying intent...")
    response = deepseek_model.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    response.pretty_print()
    raw = response.content.strip().lower()
    intent = "literature_collection" if "literature" in raw else "general"

    # Persist session_id for the lifetime of a thread; only generate on the first turn
    if state.get("session_id"):
        session_id = state["session_id"]
        turn_num = state.get("turn_num", 0) + 1
    else:
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        turn_num = 1

    # Save every turn's query to long-term memory
    _current_query = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    if _current_query:
        _save_long_memory(_current_query, session_id, turn_num)

    return {
        "intent": intent,
        "step": "intent_classified",
        "session_id": session_id,
        "turn_num": turn_num,
    }


def chat_llm_node(state: MessagesState) -> dict:
    """LLM 1：Understand the user's query, use tool calls to help solve the user's request."""
    
    system_prompt = f"""
    # Role
    You are a professional assistant skilled at analyzing user needs and providing answers based on factual knowledge

    ## Workflow
    Please complete the following tasks:
    1. Briefly summarize what the user wants to learn
    2. If there is any unknown or unclear information, generate the most suitable search engine keywords and calling the tools to get the answer.

    ## Format:
    You must always return your response in valid JSON format.

    The JSON structure must follow this schema:

    {{
        "reasoning": "Brief step-by-step reasoning process, including which tools were called and why",
        "answer": "Final answer to the user"
    }}

    ### Requirements:
    - Output must be valid JSON only
    - Do not include markdown code fences
    - Do not include additional explanations outside JSON
    - Keep reasoning concise but informative
    - The answer field should contain the final response
    
    """

    print("\n💬 [chat llm] Chatting with LLM...")
    response = search_model.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    response.pretty_print()
    return {
        "step": "llm_chatting",
        "messages": [response]
    }


def collect_paper_node(state: MessagesState) -> dict:
    """论文收集Agent节点：Collect papers based on the user's query"""
    
    system_prompt = f"""
    # Role
    You are a rigorous and efficient academic research assistant specializing in computer science, artificial intelligence, and interdisciplinary fields. 
    Your core mission is to collect high-quality academic papers based on the user’s research direction, conduct in-depth reading to extract the key innovations, and finally generate a structured and categorized survey.

    # Workflow
    When you receive a retrieval request from the user, strictly follow the steps below:

    ## Step1: Requirement Analysis
    Parse the research topic, time range, target conferences/journals, and any additional constraints provided by the user.

    ## Step2: Information Retrieval & Preliminary Screening (using search plugins/tools)
    Search for relevant papers, prioritizing those with official open-source repositories.
    Filter out papers with low relevance, without available code (unless they contain major theoretical breakthroughs), or published in low-quality venues.

    ## Step3: Taxonomy Construction
    Build a logically clear taxonomy based on the characteristics of the retrieved papers.

    ##  Step4: Structured Output
    Output the paper list according to the taxonomy, and include the required tables and information blocks.

    #Output Format Constraints
    Your response must be a JSON list, where each paper is represented using the following JSON format.

    {{
        "title": "Paper Title",
        "year": "Publish Year",
        "method": "Core Method",
        "publish": "Conference/Journal",
        "categoty": "The literature categories identified based on your analysis.",
        "code": "Code Link",
        "abstract": "Some sentences for summarizing the core idea of this paper.",
        "evaluation": "Summarize the effectiveness of the experiments in a few sentences."
    }}

    """

    _cp_round = _get_round_num(_MEM_SHORT_PAPER, state["session_id"], state["turn_num"])
    print(f"\n📚 [collect paper | turn {state['turn_num']} round {_cp_round}] Paper collecting...")

    _save_tool_results(state["messages"], state["session_id"], state["turn_num"])
    
    response = paper_collect_model.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    response.pretty_print()

    _save_short_memory(response, state["session_id"], state["turn_num"])
   
    return {
        "step": "paper_collecting",
        "messages": [response]
    }


def mysql_process_node(state: MessagesState) -> dict:
    """数据存储Agent节点：Store collected papers in MySQL database"""

    system_prompt = """
        # Role
        You are an AI expert specializing in database management, data cleaning, and structured parsing.
        Your core task is to understand complex, unstructured literature data, detect duplicate records,
        map fields precisely to the target schema, and insert only new papers.

        # Target Database
        - Schema: agentdb
        - Table: paper

        # Workflow
        1. **Schema Extraction**: Query the schema of the `paper` table using the available tools.
        2. **Existence Check**: Query the database to check whether any of the papers already exist (e.g. by title). If duplicates are found, output Branch A and stop.
        3. **Information Extraction**: Extract all paper attributes from the conversation (title, year, method, abstract, evaluation, etc.).
        4. **Data Cleaning & Alignment**: Match types to the schema (year = integer). Set missing fields to NULL. Escape special characters.
        5. **Insert**: Generate and execute an INSERT statement for every new paper.

        # Output Format
        Output strictly in ONE of the two JSON formats below.
        Do NOT include Markdown formatting or conversational filler.
        The output must be directly parsable by Python's `json.loads()`.

        ## Branch A — Records already exist in the database:
        {
            "reasoning": "Why the records were identified as duplicates.",
            "paper_summary": "Concise summary of the papers already in the database.",
            "status": "already exists"
        }

        ## Branch B — New records inserted successfully:
        {
            "reasoning": "Step-by-step: fields identified, missing fields handled, type conversions made.",
            "paper_summary": "Concise summary of the papers already in the database.",
            "insert_result": {
                "schema": "Target database name",
                "table": "Target table name",
                "sql": "INSERT INTO `schema`.`table` (`col1`, `col2`) VALUES (val1, val2);"
            },
            "status": "inserted"
        }
    """

    _mp_round = _get_round_num(_MEM_SHORT_STORE, state["session_id"], state["turn_num"])
    print(f"\n🗄️ [mysql_process | turn {state['turn_num']} round {_mp_round}] MySQL Node Processing... (Summary or Insert)")

    user_msg = next((m for m in state["messages"] if isinstance(m, HumanMessage)), None)
    paper_msg, paper_idx = None, -1

    for _i, _m in enumerate(state["messages"]):
        if isinstance(_m, AIMessage) and _has_paper_content(_m.content):
            paper_msg, paper_idx = _m, _i
            
    if paper_idx >= 0:
        mysql_phase = state["messages"][paper_idx + 1:]
        context_msgs = [m for m in [user_msg, paper_msg] if m is not None] + mysql_phase
    else:
        context_msgs = state["messages"]

    _save_tool_results(state["messages"], state["session_id"], state["turn_num"], mem_dir=_MEM_SHORT_STORE)

    response = mysql_execute_model.invoke([SystemMessage(content=system_prompt)] + context_msgs)
    response.pretty_print()

    _save_short_memory(response, state["session_id"], state["turn_num"], mem_dir=_MEM_SHORT_STORE)

    return {
        "step": "data_saving",
        "messages": [response]
    }


def route_after_classify(state: MessagesState) -> Literal["chat_llm", "collect_paper"]:
    """路由1（classify_intent → collect_paper/chat_llm）：Route to the appropriate pipeline based on classified intent"""
    if state["intent"] == "literature_collection":
        return "collect_paper"
    return "chat_llm"


def route_after_chat(state: MessagesState) -> Literal["tool_node", END]:
    """路由2（chat_llm → tool_node/END）：Continue tool loop or finish for general tasks"""
    if state["messages"][-1].tool_calls:
        return "tool_node"
    return END


def route_after_collect(state: MessagesState) -> Literal["tool_node", "mysql_process", END]:
    """路由3（收集文章->继续调用工具/数据库存储/END）：Continue collecting, abort on repeated failures or empty result, or store when done"""
    last_message = state["messages"][-1]
    
    if last_message.tool_calls:
        if _count_consecutive_failures(state["messages"]) >= 5:
            print("⚠️ Paper collection aborted: 5 consecutive tool failures.")
            return END
        return "tool_node"

    if not _has_paper_content(last_message.content):
        print("⚠️ Paper collection aborted: response contains no valid literature content.")
        return END
    
    print("\n" + "="*80 + "\n") 

    print("\n✅ Paper collection completed successfully.")

    print("\n" + "="*80 + "\n") 

    return "mysql_process"


def route_after_tool(state: MessagesState) -> Literal["chat_llm", "collect_paper", "mysql_process"]:
    """Route back to the LLM node that triggered the tool call, identified by step"""
    step = state["step"]
    if step == "llm_chatting":
        return "chat_llm"
    elif step == "paper_collecting":
        return "collect_paper"
    else:
        return "mysql_process"


def route_after_mysql(state: MessagesState) -> Literal["tool_node", "mysql_process", END]:
    """Execute pending tool calls, retry on failure, or end on success"""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "tool_node"
    
    raw = last_message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0].strip()

    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        raw = raw[start : end + 1]

    try:
        data = json.loads(raw)
        status = str(data.get("status", "")).strip().lower()
        
        if status == "already exists":
            print("\n" + "="*80 + "\n") 
            print("\n✅ MySQL node completed successfully. Summary provided!")
            print("\n" + "="*80 + "\n") 
            return END

        elif status == "inserted":
            print("\n" + "="*80 + "\n") 
            print("\n✅ MySQL node completed successfully. Records inserted!")
            print("\n" + "="*80 + "\n") 
            return END

    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return "mysql_process"


def create_search_agent(selected_model: str | None = None, env_overrides: dict | None = None, checkpointer=None):
    global search_model, paper_collect_model, mysql_execute_model

    if env_overrides:
        _apply_env_overrides(env_overrides)

    if selected_model:
        print(f"[model] Using selected model: {selected_model}")
        search_model = init_chat_model(selected_model).bind_tools(TAVILY_TOOLS)
        paper_collect_model = init_chat_model(selected_model).bind_tools(SERP_PAPER_FOUCSED_TOOLS + TAVILY_TOOLS)
        mysql_execute_model = init_chat_model(selected_model).bind_tools(MYSQL_TOOLS)
    else:
        print("[model] Using default models from .env")
        search_model = init_chat_model("deepseek:deepseek-chat").bind_tools(TAVILY_TOOLS)
        paper_collect_model = init_chat_model("deepseek:deepseek-chat").bind_tools(SERP_PAPER_FOUCSED_TOOLS + TAVILY_TOOLS)
        mysql_execute_model = init_chat_model("deepseek:deepseek-chat").bind_tools(MYSQL_TOOLS)

    workflow = StateGraph(state_schema=MessagesState)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("chat_llm", chat_llm_node)
    workflow.add_node("tool_node", tool_node)
    workflow.add_node("collect_paper", collect_paper_node)
    workflow.add_node("mysql_process", mysql_process_node)

    workflow.add_edge(START, "classify_intent")
    workflow.add_conditional_edges("classify_intent", route_after_classify, ["chat_llm", "collect_paper"])
    workflow.add_conditional_edges("chat_llm", route_after_chat, ["tool_node", END])
    workflow.add_conditional_edges("collect_paper", route_after_collect, ["tool_node", "mysql_process", END])
    workflow.add_conditional_edges("tool_node", route_after_tool, ["chat_llm", "collect_paper", "mysql_process"])
    workflow.add_conditional_edges("mysql_process", route_after_mysql, ["tool_node", "mysql_process", END])

    if checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver
        checkpointer = InMemorySaver()
    agent = workflow.compile(checkpointer=checkpointer)

    print("[agent] Graph compiled successfully.")
    _test_msg = [HumanMessage(content="Search for the latest 5 papers on LLM-based vulnerability discovery for IoT devices from 2025–2026 and summarize them.")]
    # _result = agent.invoke({"messages": _test_msg}, {"configurable": {"thread_id": "1"}})

    return agent

if __name__ == "__main__":
    create_search_agent()