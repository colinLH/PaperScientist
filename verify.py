import json
from langchain.messages import AIMessage, ToolMessage


def _count_consecutive_failures(messages: list) -> int:
    """错误恢复1：Count consecutive failed ToolMessages immediately before the last AIMessage."""
    count = 0
    for msg in reversed(messages[:-1]):
        if isinstance(msg, ToolMessage):
            text = str(msg.content).lower()
            if "unavailable" in text or "error" in text:
                count += 1
            else:
                break
        elif isinstance(msg, AIMessage):
            break
    return count


def _has_paper_content(content: str) -> bool:
    """输出验证1：Return True if the response contains at least one structured paper entry."""
    if not content or not content.strip():
        return False
    try:
        data = json.loads(content)
        if isinstance(data, list) and data:
            return isinstance(data[0], dict) and "title" in data[0]
    except (ValueError, TypeError):
        pass
    lower = content.lower()
    return "title" in lower and ("abstract" in lower or "publish" in lower or "year" in lower)
