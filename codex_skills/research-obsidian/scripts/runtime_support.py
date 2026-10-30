"""Explicit, portable runtime configuration and nonblocking process locks."""
import copy
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo


LEGACY_DOMAIN = {"name": "AI 安全", "keywords": [], "exclude_keywords": [], "sources": [], "categories": {
    "redteam": {"name": "自动化红队评估", "color": "#e0ae66"},
    "attack": {"name": "注入机制与攻击", "color": "#e17e80"},
    "alignment": {"name": "模型对齐防御", "color": "#b2a3f7"},
    "control": {"name": "执行边界与自主性", "color": "#65c8ad"},
    "general": {"name": "跨领域概念", "color": "#92b2c5"},
}}


def config_environment():
    return os.environ.get("RESEARCH_OBSIDIAN_CONFIG") or os.environ.get("AI_SAFETY_OBSIDIAN_CONFIG")


def storage_names(config):
    # Schema 1 keeps file and download names so existing links continue to work.
    if config.get("schema") == 1:
        return {"stem": "ai-safety-graph", "database": "ai-safety.lbug", "marker": "AI-SAFETY"}
    return {"stem": "research-graph", "database": "research.lbug", "marker": "RESEARCH"}


def domain_view(config):
    domain = config["domain"]
    return {"name": domain["name"], "categories": domain["categories"]}


def domain_tag(config):
    return "domain/" + (re.sub(r"[^\w-]+", "-", config["domain"]["name"]).strip("-") or "research")


def default_prefix(name):
    prefix = re.sub(r'[\[\]#|^:/\\?*<>"\x00-\x1f]', "-", name).strip().rstrip(". ")
    if not prefix or prefix in {".", ".."}:
        raise ValueError("Supply a valid --prefix for this domain")
    return prefix


def instance_identity(config):
    return {"vault_root": str(Path(config["vault_root"]).resolve()),
            "prefix": config["prefix"], "workspace": str(Path(config["workspace"]).resolve()),
            "domain": config["domain"]["name"]}


def binding_paths(config):
    return (Path(config["workspace"]) / ".research-obsidian-instance.json",
            Path(config["vault_root"]) / config["prefix"] / "系统/instance.json")


def bind_instance(config):
    identity = instance_identity(config)
    for path in binding_paths(config):
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(identity, stream, ensure_ascii=False, indent=2)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != identity:
                raise ValueError("Instance already belongs to another domain, vault or workspace")


def load_config(path=None):
    value = path or config_environment()
    if not value:
        raise ValueError("Supply --config /absolute/path/config.json; run workflow.py init first")
    file = Path(value).expanduser().resolve()
    config = json.loads(file.read_text(encoding="utf-8"))
    return validate_config(config)


def validate_config(config):
    config = copy.deepcopy(config)
    if config.get("schema") == 1:
        if config.get("domain", {}).get("name", LEGACY_DOMAIN["name"]) != LEGACY_DOMAIN["name"]:
            raise ValueError("Legacy schema 1 is an existing AI safety instance; initialize a separate schema 2 instance for another domain")
        config.setdefault("domain", copy.deepcopy(LEGACY_DOMAIN))
    elif config.get("schema") != 2:
        raise ValueError("Unsupported configuration schema; use schema 2 with an explicit domain")
    domain = config.get("domain")
    if not isinstance(domain, dict) or not isinstance(domain.get("name"), str) or not domain["name"].strip():
        raise ValueError("domain.name is required; no research field is selected by default")
    domain["name"] = domain["name"].strip()
    if any(ord(char) < 32 for char in domain["name"]):
        raise ValueError("domain.name must be a single line")
    for key in ("keywords", "exclude_keywords", "sources"):
        value = domain.setdefault(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("domain." + key + " must be a list of nonempty strings")
    categories = domain.setdefault("categories", {})
    if not isinstance(categories, dict):
        raise ValueError("domain.categories must be an object")
    for key, item in categories.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", key) or not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("Categories require a stable lowercase key and a display name")
        if "color" in item and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(item["color"])):
            raise ValueError("Category color must be #RRGGBB")
    for key in ("vault_root", "workspace"):
        if not Path(config[key]).is_absolute():
            raise ValueError(key + " must be an absolute path")
    prefix = config["prefix"]
    if not prefix or prefix in {".", ".."} or re.search(r'[\\/:*?"<>|\x00-\x1f]', prefix):
        raise ValueError("prefix must be one valid directory name")
    vault = Path(config["vault_root"]).resolve()
    if not (vault / prefix).resolve().is_relative_to(vault):
        raise ValueError("Knowledge directory escapes the vault")
    if Path(config["workspace"]).resolve().is_relative_to(vault):
        raise ValueError("Keep runtime workspace outside the Obsidian vault")
    ZoneInfo(config["timezone"])
    if type(config["papers_per_day"]) is not int or config["papers_per_day"] < 1:
        raise ValueError("papers_per_day must be a positive integer")
    for key in ("collect_at", "sync_at"):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", config[key]):
            raise ValueError(key + " must be HH:MM")
    site = config.get("site", {})
    if site.get("enabled") and (not site.get("project_id") or not site.get("url")):
        raise ValueError("Enabled Sites publishing requires project_id and url")
    for path in binding_paths(config):
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != instance_identity(config):
            raise ValueError("This workspace or vault section belongs to another domain; use a separate workspace and prefix")
    if config["schema"] == 2 and not binding_paths(config)[0].exists():
        work = Path(config["workspace"])
        if (work / "work/sync/current.json").exists() or (work / "work/site/data/state.json").exists():
            raise ValueError("Existing graph workspace has no matching domain binding; use a separate workspace")
    # Do not reinterpret an unbound legacy dataset by editing the schema field.
    index = vault / prefix / "系统/collection-index.json"
    if config["schema"] == 2 and index.exists() and json.loads(index.read_text(encoding="utf-8")).get("schema") == "ai-safety-obsidian/1":
        raise ValueError("Legacy archive must keep its original schema 1 config; use a new section for a new domain")
    return config


def canonical_arxiv(value):
    value = str(value or "").strip()
    value = re.sub(r"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)", "", value, flags=re.I)
    value = re.sub(r"\.pdf$", "", value, flags=re.I)
    value = re.sub(r"v\d+$", "", value, flags=re.I)
    if value and not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})", value, flags=re.I):
        raise ValueError("Invalid arXiv identifier")
    return value.lower()


def canonical_doi(value):
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value or "").strip(), flags=re.I).lower()
    if value and not re.fullmatch(r"10\.\d{4,9}/\S+", value):
        raise ValueError("Invalid DOI")
    return value


def canonical_pmid(value):
    value = re.sub(r"^(?:https?://pubmed\.ncbi\.nlm\.nih\.gov/|pmid:\s*)", "", str(value or "").strip(), flags=re.I).rstrip("/")
    if value and not re.fullmatch(r"[1-9]\d*", value):
        raise ValueError("Invalid PMID")
    return value


@contextmanager
def file_lock(path):
    """OS-owned lock: crashes release it; concurrent jobs fail without stealing it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
