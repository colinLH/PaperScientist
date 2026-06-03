"""
Tavily 网页搜索工具
==================
暴露接口一览
-----------
1. tavily_web_search(query: str) -> str
   - LangChain @tool 装饰器包装，可直接挂载到 LangGraph ToolNode / create_react_agent。
   - 参数: query — 搜索关键词字符串。
   - 返回: 格式化的搜索摘要字符串（供 LLM 直接阅读）。

2. search_web(query: str, max_results: int = 5) -> list[dict]
   - 原始调用，返回 Tavily API 的结构化结果列表。
   - 每个 dict 包含: title, url, content, score。
   - 适合需要自行处理原始数据的场景。

3. search_web_formatted(query: str, max_results: int = 5) -> str
   - 调用 search_web 并将结果格式化为易读的 Markdown 字符串。
   - 适合直接填充 SearchState.search_results 字段。

4. TAVILY_TOOLS: list
   - 包含 [tavily_web_search] 的列表，方便一行注册到 agent。
   - 示例: agent = create_react_agent(llm, tools=TAVILY_TOOLS)

环境变量
--------
TAVILY_API_KEY — 必须在 .env 或系统环境变量中设置。
"""

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

load_dotenv()

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "TAVILY_API_KEY not found. Please set it in your .env file or system environment variables."
            )
        _client = TavilyClient(api_key=api_key)
    return _client


def search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    执行 Tavily 网页搜索，返回原始结构化结果。

    参数
    ----
    query       : 搜索关键词。
    max_results : 最多返回的结果条数，默认 5。

    返回
    ----
    list[dict]，每条结果包含:
        - title   (str)  : 页面标题
        - url     (str)  : 页面链接
        - content (str)  : 摘要内容
        - score   (float): 相关性评分
    """
    client = _get_client()
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_answer=False,
    )
    results = []
    for item in response.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0.0),
            }
        )
    return results


def search_web_formatted(query: str, max_results: int = 5) -> str:
    """
    执行 Tavily 网页搜索，返回格式化的 Markdown 字符串。

    参数
    ----
    query       : 搜索关键词。
    max_results : 最多返回的结果条数，默认 5。

    返回
    ----
    str — 可直接赋值给 SearchState.search_results 的 Markdown 文本。
    """
    results = search_web(query=query, max_results=max_results)
    if not results:
        return f"No search results found for: {query}"

    lines = [f"## Search Results: {query}\n"]
    for idx, item in enumerate(results, start=1):
        lines.append(f"### {idx}. {item['title']}")
        lines.append(f"- **URL**: {item['url']}")
        lines.append(f"- **Score**: {item['score']:.2f}")
        lines.append(f"- **Summary**: {item['content']}\n")
    return "\n".join(lines)


@tool
def tavily_web_search(query: str) -> str:
    """
    Use the Tavily API to search the internet and retrieve the latest webpage content summaries related to the query.

    Parameters
    ----------
    query : The keyword or question to search for.

    Returns
    -------
    str — Formatted search results containing titles, links, and summaries.
    """
    return search_web_formatted(query=query, max_results=5)


TAVILY_TOOLS = [tavily_web_search]
