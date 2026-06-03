from fastapi import FastAPI, HTTPException
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import uvicorn

load_dotenv()

app = FastAPI(
    title="MySQL SQL Tool",
    description="MySQL SQL query and execution tool for Dify Agent/Workflow",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Database engine (singleton, lazy-validated via pool_pre_ping)
# ---------------------------------------------------------------------------

def _build_engine():
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)

engine = _build_engine()

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    sql: str = Field(..., description="SQL SELECT statement to execute")
    limit: Optional[int] = Field(200, ge=1, le=2000, description="Maximum rows to return (1-2000, default 200)")

class ExecuteRequest(BaseModel):
    sql: str = Field(..., description="SQL DML/DDL statement to execute (INSERT / UPDATE / DELETE / CREATE / ALTER / DROP)")

class QueryResult(BaseModel):
    columns: List[str] = Field(..., description="Column names in order")
    rows: List[Dict[str, Any]] = Field(..., description="Result rows as list of dicts")
    row_count: int = Field(..., description="Number of rows returned")

class ExecuteResult(BaseModel):
    affected_rows: int = Field(..., description="Number of rows affected")
    message: str = Field(..., description="Execution result message")

class SchemaResult(BaseModel):
    table: str
    columns: List[Dict[str, Any]] = Field(..., description="Column definitions (Field, Type, Null, Key, Default, Extra)")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    summary="Health check",
    description="Verify the service and database connection are alive.",
    tags=["System"],
)
def health_check() -> Dict[str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": os.getenv("MYSQL_DATABASE", "")}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {e}")


@app.get(
    "/tables",
    summary="List all tables",
    description="Return a list of all table names in the current database.",
    tags=["Schema"],
)
def list_tables() -> Dict[str, List[str]]:
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]
        return {"tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/schema/{table_name}",
    summary="Get table schema",
    description="Return column definitions (name, type, nullable, key, default, extra) for the given table.",
    tags=["Schema"],
    response_model=SchemaResult,
)
def get_schema(table_name: str) -> SchemaResult:
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"DESCRIBE `{table_name}`"))
            columns = [dict(row._mapping) for row in result]
        return SchemaResult(table=table_name, columns=columns)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/query",
    summary="Execute SQL SELECT query",
    description=(
        "Execute a read-only SELECT statement and return results as JSON. "
        "Non-SELECT statements are rejected. Use the `limit` field to cap returned rows."
    ),
    tags=["SQL"],
    response_model=QueryResult,
)
def execute_query(req: QueryRequest) -> QueryResult:
    sql = req.sql.strip()
    if not sql.upper().lstrip("(").startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT statements are allowed on /query. Use /execute for DML/DDL.",
        )
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result]
        if req.limit:
            rows = rows[: req.limit]
        return QueryResult(columns=keys, rows=rows, row_count=len(rows))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/execute",
    summary="Execute SQL DML/DDL statement",
    description=(
        "Execute a write statement: INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, TRUNCATE, etc. "
        "The statement runs inside a transaction that is auto-committed on success."
    ),
    tags=["SQL"],
    response_model=ExecuteResult,
)
def execute_statement(req: ExecuteRequest) -> ExecuteResult:
    sql = req.sql.strip()
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql))
            affected = result.rowcount if result.rowcount is not None else -1
        return ExecuteResult(
            affected_rows=affected,
            message=f"Statement executed successfully. Rows affected: {affected}.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("TOOL_HOST", "0.0.0.0")
    port = int(os.getenv("TOOL_PORT", "8088"))
    uvicorn.run("sql:app", host=host, port=port, reload=False)

# http://127.0.0.1:8088/openapi.json
