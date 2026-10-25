from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import dotenv_values
from .credentials import load_credentials

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / ".paperscientist"
    model: str = "deepseek:deepseek-chat"
    context_tokens: int = 64000
    output_tokens: int = 4096
    max_steps: int = 24
    max_subagents: int = 3
    max_agent_depth: int = 2
    max_agent_tasks: int = 64
    agent_profiles_path: Path | None = None
    tool_timeout: float = 90
    allow_execution: bool = False
    extract_memory: bool = True
    skill_roots: tuple[Path, ...] = (ROOT / "research_skills", ROOT / "external_skills")
    credentials: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, **overrides):
        local_file = ROOT / "paperscientist.local.json"
        local = json.loads(local_file.read_text(encoding="utf-8")) if local_file.is_file() else {}
        # Only non-secret workspace preferences may be read from this file.
        values = {**load_credentials(), **{k: str(v) for k, v in local.items() if k in {"PS_DATA_DIR", "PS_MODEL"}}, **dotenv_values(ROOT / ".env"), **os.environ}
        model = values.get("PS_MODEL") or (
            "deepseek:deepseek-chat" if values.get("DEEPSEEK_API_KEY") else
            "google_genai:gemini-2.5-flash" if values.get("GOOGLE_API_KEY") else
            "openai:gpt-4.1" if values.get("OPENAI_API_KEY") else "demo"
        )
        roots = [ROOT / "research_skills", ROOT / "external_skills"]
        roots.extend(Path(p).expanduser() for p in values.get("PS_SKILL_ROOTS", "").split(os.pathsep) if p)
        return cls(
            data_dir=(ROOT / Path(values.get("PS_DATA_DIR") or ".paperscientist")).resolve(),
            model=model,
            context_tokens=int(values.get("PS_CONTEXT_TOKENS", 64000)),
            output_tokens=int(values.get("PS_OUTPUT_TOKENS", 4096)),
            max_steps=int(values.get("PS_MAX_STEPS", 24)),
            max_subagents=int(values.get("PS_MAX_SUBAGENTS", 3)),
            max_agent_depth=int(values.get("PS_MAX_AGENT_DEPTH", 2)),
            max_agent_tasks=int(values.get("PS_MAX_AGENT_TASKS", 64)),
            agent_profiles_path=Path(values["PS_AGENT_PROFILES"]).expanduser().resolve() if values.get("PS_AGENT_PROFILES") else None,
            tool_timeout=float(values.get("PS_TOOL_TIMEOUT", 90)),
            allow_execution=values.get("PS_ALLOW_EXECUTION", "false").lower() == "true",
            extract_memory=values.get("PS_EXTRACT_MEMORY", "true").lower() == "true",
            skill_roots=tuple(roots),
            credentials={k: str(v) for k, v in values.items() if v and (
                k.endswith("_API_KEY") or k in {"OPENAI_BASE_URL", "DEEPSEEK_API_BASE"}
            )},
        ).with_overrides(**overrides)

    def with_overrides(self, **kwargs):
        allowed = {k: v for k, v in kwargs.items() if v is not None and k in self.__dataclass_fields__}
        result = replace(self, **allowed)
        if not 2048 <= result.context_tokens <= 2000000:
            raise ValueError("context_tokens must be between 2048 and 2000000")
        if not 1 <= result.max_steps <= 100 or not 1 <= result.max_subagents <= 8:
            raise ValueError("Invalid agent budget")
        if not 1 <= result.max_agent_depth <= 5 or not 1 <= result.max_agent_tasks <= 256:
            raise ValueError("Invalid agent hierarchy budget")
        if not 256 <= result.output_tokens < result.context_tokens:
            raise ValueError("output_tokens must fit inside context_tokens")
        return result


def create_model(settings: Settings):
    """Create a request-local model; never mutate process environment or globals."""
    provider, sep, name = settings.model.partition(":")
    if not sep:
        raise ValueError("Use provider:model, for example deepseek:deepseek-chat")
    common = {"model": name, "max_tokens": settings.output_tokens, "timeout": 120, "max_retries": 2}
    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(**common, api_key=settings.credentials.get("DEEPSEEK_API_KEY"),
                            **({"api_base": settings.credentials["DEEPSEEK_API_BASE"]}
                               if settings.credentials.get("DEEPSEEK_API_BASE") else {}))
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**common, api_key=settings.credentials.get("OPENAI_API_KEY"),
                          **({"base_url": settings.credentials["OPENAI_BASE_URL"]}
                             if settings.credentials.get("OPENAI_BASE_URL") else {}))
    if provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(**common, google_api_key=settings.credentials.get("GOOGLE_API_KEY"))
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(**common, api_key=settings.credentials.get("ANTHROPIC_API_KEY"))
    raise ValueError(f"Unsupported provider: {provider}")
