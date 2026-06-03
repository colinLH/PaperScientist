"""
SerpAPI 搜索工具
================
暴露接口一览
-----------
1. serp_google_search(query: str) -> str
   - LangChain @tool 装饰器包装，可直接挂载到 LangGraph ToolNode / create_react_agent。
   - 参数: query — 搜索关键词字符串。
   - 返回: 格式化的 Google 搜索摘要字符串（供 LLM 直接阅读）。

2. serp_google_scholar_search(query: str, ...) -> str
   - LangChain @tool 装饰器包装，可直接挂载到 LangGraph ToolNode / create_react_agent。
   - 参数: query — 搜索关键词字符串；支持 Google Scholar 所有可选过滤参数。
   - 返回: 格式化的 Google Scholar 学术搜索摘要字符串（供 LLM 直接阅读）。

3. search_google(query: str, max_results: int = 5) -> list[dict]
   - 原始调用，返回 Google 搜索的结构化结果列表。
   - 每个 dict 包含: title, url, snippet。
   - 适合需要自行处理原始数据的场景。

4. search_google_formatted(query: str, max_results: int = 5) -> str
   - 调用 search_google 并将结果格式化为易读的 Markdown 字符串。
   - 适合直接填充 SearchState.search_results 字段。

5. search_google_scholar(query: str, max_results: int = 10, ...) -> list[dict]
   - 原始调用，返回 Google Scholar 学术搜索的结构化结果列表。
   - 每个 dict 包含: title, url, snippet, publication_info, cited_by_count。
   - 支持 Google Scholar 所有可选过滤参数（年份范围、排序、语言等）。
   - 适合需要自行处理原始数据的场景。

6. search_google_scholar_formatted(query: str, max_results: int = 10, ...) -> str
   - 调用 search_google_scholar 并将结果格式化为易读的 Markdown 字符串。
   - 适合直接填充 SearchState.search_results 字段。

7. SERP_API_TOOLS: list
   - 包含 [serp_google_search, serp_google_scholar_search] 的列表，方便一行注册到 agent。
   - 示例: agent = create_react_agent(llm, tools=SERP_API_TOOLS)

环境变量
--------
SERPAPI_API_KEY — 必须在 .env 或系统环境变量中设置。
"""

import os
from typing import Any

import serpapi
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

_client: serpapi.Client | None = None


def _get_client() -> serpapi.Client:
    global _client
    if _client is None:
        api_key = os.getenv("SERPAPI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "SERPAPI_API_KEY not found. Please set it in your .env file or system environment variables."
            )
        _client = serpapi.Client(api_key=api_key)
    return _client


def search_google(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    执行 Google 网页搜索，返回原始结构化结果。

    参数
    ----
    query       : 搜索关键词。
    max_results : 最多返回的结果条数，默认 5。

    返回
    ----
    list[dict]，每条结果包含:
        - title   (str): 页面标题
        - url     (str): 页面链接
        - snippet (str): 摘要内容
    """
    client = _get_client()
    response = client.search(
        {
            "engine": "google",
            "q": query,
            "num": max_results,
        }
    )
    results = []
    for item in response.get("organic_results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return results[:max_results]


def search_google_formatted(query: str, max_results: int = 5) -> str:
    """
    执行 Google 网页搜索，返回格式化的 Markdown 字符串。

    参数
    ----
    query       : 搜索关键词。
    max_results : 最多返回的结果条数，默认 5。

    返回
    ----
    str — 可直接赋值给 SearchState.search_results 的 Markdown 文本。
    """
    results = search_google(query=query, max_results=max_results)
    if not results:
        return f"No Google search results found for: {query}"

    lines = [f"## Google Search Results: {query}\n"]
    for idx, item in enumerate(results, start=1):
        lines.append(f"### {idx}. {item['title']}")
        lines.append(f"- **URL**: {item['url']}")
        lines.append(f"- **Snippet**: {item['snippet']}\n")
    return "\n".join(lines)


def search_google_scholar(
    query: str,
    max_results: int = 10,
    cites: str | None = None,
    as_ylo: int | None = None,
    as_yhi: int | None = None,
    scisbd: int | None = None,
    cluster: str | None = None,
    hl: str | None = None,
    lr: str | None = None,
    start: int | None = None,
    as_sdt: str | None = None,
    safe: str | None = None,
    filter: int | None = None,
    as_vis: int | None = None,
    as_rr: int | None = None,
    no_cache: bool | None = None,
) -> list[dict[str, Any]]:
    """
    执行 Google Scholar 学术搜索，返回原始结构化结果。

    参数
    ----
    query       : 搜索关键词。
    max_results : 最多返回的结果条数，默认 10。
    cites       : 文章 ID，用于"引用此文"搜索。示例: 1275980731835430123。
    as_ylo      : 起始年份筛选（含）。示例: 2018。
    as_yhi      : 截止年份筛选（含）。示例: 2024。
    scisbd      : 排序方式：0=按相关性（默认），1=仅摘要，2=全部。
    cluster     : 文章集群 ID，用于"所有版本"搜索，不能与 cites 同时使用。
    hl          : 界面语言代码。示例: en, zh, fr，默认: en。
    lr          : 结果语言过滤。示例: lang_en|lang_zh。
    start       : 分页偏移量，0=第1页，10=第2页，默认: 0。
    as_sdt      : 搜索类型/过滤器。0=排除专利（默认），7=包含专利，4=判例法。
    safe        : 安全内容过滤：'active' 或 'off'。
    filter      : 相似/省略结果过滤：1=启用（默认），0=禁用。
    as_vis      : 引用结果：0=包含（默认），1=排除。
    as_rr       : 仅综述文章：0=全部（默认），1=仅综述。
    no_cache    : 强制获取新结果，绕过 SerpApi 缓存，默认: False。

    返回
    ----
    list[dict]，每条结果包含:
        - title            (str): 论文标题
        - url              (str): 论文链接
        - snippet          (str): 摘要内容
        - publication_info (str): 作者、期刊、年份等发布信息
        - cited_by_count   (int): 引用次数
    """
    client = _get_client()
    params: dict[str, Any] = {
        "engine": "google_scholar",
        "q": query,
        "num": max_results,
    }
    optional_fields = {
        "cites": cites,
        "as_ylo": as_ylo,
        "as_yhi": as_yhi,
        "scisbd": scisbd,
        "cluster": cluster,
        "hl": hl,
        "lr": lr,
        "start": start,
        "as_sdt": as_sdt,
        "safe": safe,
        "filter": filter,
        "as_vis": as_vis,
        "as_rr": as_rr,
        "no_cache": no_cache,
    }
    for key, val in optional_fields.items():
        if val is not None:
            params[key] = val
    response = client.search(params)
    results = []
    for item in response.get("organic_results", []):
        inline_links = item.get("inline_links", {})
        cited_by = inline_links.get("cited_by", {})
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "publication_info": item.get("publication_info", {}).get("summary", ""),
                "cited_by_count": cited_by.get("total", 0),
            }
        )
    return results[:max_results]


def search_google_scholar_formatted(
    query: str,
    max_results: int = 10,
    cites: str | None = None,
    as_ylo: int | None = None,
    as_yhi: int | None = None,
    scisbd: int | None = None,
    cluster: str | None = None,
    hl: str | None = None,
    lr: str | None = None,
    start: int | None = None,
    as_sdt: str | None = None,
    safe: str | None = None,
    filter: int | None = None,
    as_vis: int | None = None,
    as_rr: int | None = None,
    no_cache: bool | None = None,
) -> str:
    """
    执行 Google Scholar 学术搜索，返回格式化的 Markdown 字符串。

    参数
    ----
    query       : 搜索关键词。
    max_results : 最多返回的结果条数，默认 10。
    （其余参数参见 search_google_scholar 的说明）

    返回
    ----
    str — 可直接赋值给 SearchState.search_results 的 Markdown 文本。
    """
    results = search_google_scholar(
        query=query,
        max_results=max_results,
        cites=cites,
        as_ylo=as_ylo,
        as_yhi=as_yhi,
        scisbd=scisbd,
        cluster=cluster,
        hl=hl,
        lr=lr,
        start=start,
        as_sdt=as_sdt,
        safe=safe,
        filter=filter,
        as_vis=as_vis,
        as_rr=as_rr,
        no_cache=no_cache,
    )
    if not results:
        return f"No Google Scholar results found for: {query}"

    lines = [f"## Google Scholar Search Results: {query}\n"]
    for idx, item in enumerate(results, start=1):
        lines.append(f"### {idx}. {item['title']}")
        lines.append(f"- **URL**: {item['url']}")
        lines.append(f"- **Publication**: {item['publication_info']}")
        lines.append(f"- **Cited by**: {item['cited_by_count']}")
        lines.append(f"- **Abstract**: {item['snippet']}\n")
    return "\n".join(lines)


@tool
def serp_google_search(query: str) -> str:
    """
    Use the SerpAPI to perform a Google web search and retrieve the latest webpage content summaries related to the query.

    Parameters
    ----------
    query : The keyword or question to search for.

    Returns
    -------
    str — Formatted search results containing titles, links, and snippets.
    """
    return search_google_formatted(query=query, max_results=5)


@tool
def serp_google_scholar_search(
    query: str,
    max_results: int = 10,
    cites: str | None = None,
    as_ylo: int | None = None,
    as_yhi: int | None = None,
    scisbd: int | None = None,
    cluster: str | None = None,
    hl: str | None = None,
    lr: str | None = None,
    start: int | None = None,
    as_sdt: str | None = None,
    safe: str | None = None,
    filter: int | None = None,
    as_vis: int | None = None,
    as_rr: int | None = None,
    no_cache: bool | None = None,
) -> str:
    """
    Use the SerpAPI to search Google Scholar for academic papers, articles, and citations related to the query.

    Parameters
    ----------
    query       : The keyword, topic, or research question to search for.
    max_results : Maximum number of results to return. Default: 10.
    cites       : Article ID for Cited By searches. Example: 1275980731835430123.
    as_ylo      : Include results from this year onwards. Example: 2018.
    as_yhi      : Include results up to this year. Example: 2024.
    scisbd      : Sort by date: 0=by relevance (default), 1=abstracts only, 2=everything.
    cluster     : Article cluster ID for All Versions searches. Use alone without cites.
    hl          : Interface language code. Example: en, zh, fr. Default: en.
    lr          : Results language filter. Example: lang_en|lang_zh.
    start       : Result offset for pagination. 0=page 1, 10=page 2. Default: 0.
    as_sdt      : Search type or filter. 0=exclude patents (default), 7=include patents, 4=case law.
    safe        : Adult content filter: 'active' or 'off'.
    filter      : Similar/Omitted results filter: 1=enabled (default), 0=disabled.
    as_vis      : Citation results: 0=include (default), 1=exclude.
    as_rr       : Review articles only: 0=all results (default), 1=review articles only.
    no_cache    : Force fresh results, bypass SerpApi cache. Default: False.

    Returns
    -------
    str — Formatted academic search results containing titles, links, publication info, citation counts, and abstracts.
    """
    return search_google_scholar_formatted(
        query=query,
        max_results=max_results,
        cites=cites,
        as_ylo=as_ylo,
        as_yhi=as_yhi,
        scisbd=scisbd,
        cluster=cluster,
        hl=hl,
        lr=lr,
        start=start,
        as_sdt=as_sdt,
        safe=safe,
        filter=filter,
        as_vis=as_vis,
        as_rr=as_rr,
        no_cache=no_cache,
    )


SERP_API_TOOLS = [serp_google_search, serp_google_scholar_search]
SERP_PAPER_FOUCSED_TOOLS = [serp_google_scholar_search]
