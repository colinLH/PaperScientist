"""Reject partial generations before they can cause tool side effects."""
from langchain_core.messages import AIMessage


def require_complete(response):
    if not isinstance(response, AIMessage):
        raise TypeError("Model must return AIMessage")
    reason = str(response.response_metadata.get("finish_reason") or response.response_metadata.get("stop_reason") or "").lower()
    if reason in {"length", "max_tokens", "max_output_tokens", "model_length"} or response.invalid_tool_calls:
        raise ValueError("模型输出未完整结束；未执行任何工具。请将文件拆成较小模块或提高输出上限。")
    return response
