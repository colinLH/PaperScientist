"""
MySQL SQL 执行工具
==================
暴露接口一览
-----------
1. mysql_query(sql: str, limit: int = 200) -> str
   - LangChain @tool 装饰器包装，执行只读 SELECT 语句并返回结果。
   - 参数: sql — SELECT 语句；limit — 最多返回行数（默认 200）。
   - 返回: 格式化的查询结果字符串（供 LLM 直接阅读）。

2. mysql_execute(sql: str) -> str
   - LangChain @tool 装饰器包装，执行写入语句（INSERT / UPDATE / DELETE / DDL）。
   - 参数: sql — DML 或 DDL 语句。
   - 返回: 执行结果摘要字符串。

3. mysql_list_tables() -> str
   - LangChain @tool 装饰器包装，列出当前数据库的所有表名。
   - 返回: 格式化的表名列表字符串。

4. mysql_describe_table(table_name: str) -> str
   - LangChain @tool 装饰器包装，返回指定表的列定义。
   - 参数: table_name — 表名。
   - 返回: 格式化的表结构字符串。

5. run_query(sql: str, limit: int = 200) -> list[dict]
   - 原始调用，返回 SELECT 结果的结构化列表。
   - 每个 dict 对应一行，键为列名。

6. run_execute(sql: str) -> dict
   - 原始调用，执行写入语句，返回包含 affected_rows 的 dict。

7. MYSQL_TOOLS: list
   - 包含所有 MySQL 工具的列表，方便一行注册到 agent。
   - 示例: agent = create_react_agent(llm, tools=MYSQL_TOOLS)

数据库配置
----------
从 .env 中读取以下环境变量:
    MYSQL_HOST     — 数据库主机（默认 127.0.0.1）
    MYSQL_PORT     — 端口（默认 3306）
    MYSQL_USER     — 用户名（默认 root）
    MYSQL_PASSWORD — 密码
    MYSQL_DATABASE — 数据库名
"""

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        host = os.getenv("MYSQL_HOST", "127.0.0.1")
        port = os.getenv("MYSQL_PORT", "3306")
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "")
        database = os.getenv("MYSQL_DATABASE", "")
        if not database:
            raise EnvironmentError(
                "MYSQL_DATABASE not found. Please set it in .env."
            )
        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _engine


def run_query(sql: str, limit: int = 200) -> list[dict[str, Any]]:
    """
    执行只读 SELECT 语句，返回原始结构化结果。

    参数
    ----
    sql   : SELECT 语句。
    limit : 最多返回行数，默认 200。

    返回
    ----
    list[dict]，每条记录为一个 dict，键为列名。

    异常
    ----
    ValueError  : 传入非 SELECT 语句时抛出。
    RuntimeError: 数据库执行失败时抛出。
    """
    if not sql.strip().upper().lstrip("(").startswith("SELECT"):
        raise ValueError("run_query only accepts SELECT statements. Use run_execute for DML/DDL.")
    try:
        with _get_engine().connect() as conn:
            result = conn.execute(text(sql))
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result]
        return rows[:limit]
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Query failed: {e}") from e


def run_execute(sql: str) -> dict[str, Any]:
    """
    执行写入语句（INSERT / UPDATE / DELETE / DDL），返回执行结果摘要。

    参数
    ----
    sql : DML 或 DDL 语句。

    返回
    ----
    dict，包含:
        - affected_rows (int): 受影响行数（DDL 语句通常为 -1）
        - message       (str): 执行结果描述

    异常
    ----
    RuntimeError: 数据库执行失败时抛出。
    """
    try:
        with _get_engine().begin() as conn:
            result = conn.execute(text(sql))
            affected = result.rowcount if result.rowcount is not None else -1
        return {
            "affected_rows": affected,
            "message": f"Statement executed successfully. Rows affected: {affected}.",
        }
    except Exception as e:
        raise RuntimeError(f"Execute failed: {e}") from e


@tool
def mysql_query(sql: str, limit: int = 200) -> str:
    """
    Execute a SQL SELECT statement against the MySQL database and return the results.

    Parameters
    ----------
    sql   : A valid SQL SELECT statement.
    limit : Maximum number of rows to return (default 200, max 2000).

    Returns
    -------
    str — Formatted query results as a Markdown table, or an error message.
    """
    try:
        rows = run_query(sql=sql, limit=min(limit, 2000))
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"

    if not rows:
        return "Query executed successfully. No rows returned."

    columns = list(rows[0].keys())
    header = " | ".join(columns)
    separator = " | ".join(["---"] * len(columns))
    lines = [f"| {header} |", f"| {separator} |"]
    for row in rows:
        line = " | ".join(str(row.get(c, "")) for c in columns)
        lines.append(f"| {line} |")
    lines.append(f"\n_{len(rows)} row(s) returned._")
    return "\n".join(lines)


@tool
def mysql_execute(sql: str) -> str:
    """
    Execute a SQL write statement (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, TRUNCATE) against the MySQL database.

    Parameters
    ----------
    sql : A valid SQL DML or DDL statement.

    Returns
    -------
    str — Execution result summary, or an error message.
    """
    try:
        result = run_execute(sql=sql)
        return result["message"]
    except RuntimeError as e:
        return f"Error: {e}"


@tool
def mysql_list_tables() -> str:
    """
    List all table names in the current MySQL database.

    Returns
    -------
    str — A formatted list of table names, or an error message.
    """
    try:
        with _get_engine().connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]
    except Exception as e:
        return f"Error: {e}"

    if not tables:
        return "No tables found in the database."

    lines = ["**Tables in database:**\n"]
    for t in tables:
        lines.append(f"- `{t}`")
    return "\n".join(lines)


@tool
def mysql_describe_table(table_name: str) -> str:
    """
    Return the column definitions (name, type, nullable, key, default, extra) for the given MySQL table.

    Parameters
    ----------
    table_name : The name of the table to describe.

    Returns
    -------
    str — Formatted table schema as a Markdown table, or an error message.
    """
    try:
        with _get_engine().connect() as conn:
            result = conn.execute(text(f"DESCRIBE `{table_name}`"))
            columns = [dict(row._mapping) for row in result]
    except Exception as e:
        return f"Error: {e}"

    if not columns:
        return f"No schema found for table `{table_name}`."

    keys = list(columns[0].keys())
    header = " | ".join(keys)
    separator = " | ".join(["---"] * len(keys))
    lines = [f"**Schema of `{table_name}`:**\n", f"| {header} |", f"| {separator} |"]
    for col in columns:
        line = " | ".join(str(col.get(k, "")) for k in keys)
        lines.append(f"| {line} |")
    return "\n".join(lines)


MYSQL_TOOLS = [mysql_query, mysql_execute, mysql_list_tables, mysql_describe_table]