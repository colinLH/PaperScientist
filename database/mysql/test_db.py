import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

load_dotenv()


def test_mysql_connection(
    host: str = None,
    port: str = None,
    user: str = None,
    password: str = None,
    database: str = None,
) -> dict:
    """
    Test MySQL connectivity with the given (or env-derived) parameters.

    Returns a dict with keys:
        success  (bool)
        url      (str)   — connection URL with password masked
        message  (str)   — human-readable result or error detail
    """
    host     = host     or os.getenv("MYSQL_HOST",     "127.0.0.1")
    # host     = host     or os.getenv("MYSQL_HOST",     "172.19.112.1")
    port     = port     or os.getenv("MYSQL_PORT",     "3306")
    user     = user     or os.getenv("MYSQL_USER",     "root")
    password = password or os.getenv("MYSQL_PASSWORD", "")
    database = database or os.getenv("MYSQL_DATABASE", "")

    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    masked_url = f"mysql+pymysql://{user}:***@{host}:{port}/{database}"

    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        engine.dispose()
        return {"success": True, "url": masked_url, "message": "Connection successful."}
    except OperationalError as e:
        return {"success": False, "url": masked_url, "message": f"OperationalError: {e.orig}"}
    except SQLAlchemyError as e:
        return {"success": False, "url": masked_url, "message": f"SQLAlchemyError: {e}"}
    except Exception as e:
        return {"success": False, "url": masked_url, "message": f"Unexpected error: {e}"}


# ---------------------------------------------------------------------------
# pytest-compatible test (picked up automatically by pytest)
# ---------------------------------------------------------------------------

def test_connection_from_env():
    """Pytest: verify that env-configured MySQL is reachable."""
    result = test_mysql_connection()
    assert result["success"], f"MySQL connection failed — {result['message']}"


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = test_mysql_connection()
    status = "PASS" if result["success"] else "FAIL"
    print(f"[{status}] {result['url']}")
    print(f"       {result['message']}")
    sys.exit(0 if result["success"] else 1)
