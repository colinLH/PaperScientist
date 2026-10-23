"""Compatibility entrypoint for notebooks and LangGraph Studio.

The active implementation lives in paperscientist/. The original fixed pipeline
is preserved under legacy/ for comparison.
"""
from __future__ import annotations
import uuid
from typing import Annotated, TypedDict
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from paperscientist.config import Settings
from paperscientist.memory import text_content
from paperscientist.runtime import AgentService

AVAILABLE_MODELS = {"deepseek":["deepseek-chat","deepseek-reasoner"],
                    "google_genai":["gemini-2.5-flash"],"openai":["gpt-4.1"]}

class ResearchState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    session_id: str
    project_id: str
    artifacts: list

def create_search_agent(selected_model=None, env_overrides=None, checkpointer=None, use_mcp_tools=False):
    settings = Settings.load(model=selected_model)
    if env_overrides:
        allowed = {k:v for k,v in env_overrides.items() if k.endswith("_API_KEY") or k == "OPENAI_BASE_URL"}
        settings = settings.with_overrides(credentials={**settings.credentials,**allowed})
    service = AgentService(settings)

    async def research(state: ResearchState, config: RunnableConfig):
        sid = state.get("session_id") or str(config.get("configurable",{}).get("thread_id") or uuid.uuid4().hex)
        user = next((m for m in reversed(state["messages"]) if m.type == "human"),None)
        if user is None:
            raise ValueError("A user message is required")
        result = await service.run_turn(sid,text_content(user),project_id=state.get("project_id","default"))
        return {"messages":[AIMessage(content=result["content"])],"session_id":sid,"artifacts":result["artifacts"]}

    graph = StateGraph(ResearchState)
    graph.add_node("research",research)
    graph.add_edge(START,"research")
    graph.add_edge("research",END)
    return graph.compile(checkpointer=checkpointer)
