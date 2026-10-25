# PaperScientist Agent Notes

## Docker Milvus Lite Architecture

PaperScientist uses a Docker-hosted Milvus Lite service to work around Windows not supporting Milvus Lite natively.

### Data flow

- **Windows side**: PDF → Markdown → `HierarchicalNodes` → embedding with `Qwen3-VL-Embedding-2B` (dim=2048) → HTTP POST to the Docker service.
- **Docker side** (Ubuntu 22.04): FastAPI service on port `8000` + Milvus Lite, storing data in the shared volume at `e:\agent\ragagent\data_store\database\milvus.db`.

### Key files

| File | Purpose |
|------|---------|
| `docker/Dockerfile` | Ubuntu 22.04 + `pymilvus` + FastAPI |
| `docker/docker-compose.yml` | Port `8000`, volume mount `../` → `/workspace/agent` |
| `docker/milvus_service.py` | FastAPI REST service: `/upsert`, `/stats`, `/health`, `/document/{name}` |
| `docker/start.bat` / `docker/stop.bat` | Convenience scripts |
| `ragagent/data_store/remote_milvus_store.py` | Windows HTTP client (`RemoteMilvusNodeStore`) |
| `ragagent/agent.py` | Uses `RemoteMilvusNodeStore` |

### Runtime

- Default service URL: `http://localhost:8000`
- Start: `docker-compose up -d --build` from `docker/`
- Optional env: `MILVUS_SERVICE_URL`

### Known model/API fixes

- `VECTOR_DIM` must be `2048` (matches `Qwen3-VL-Embedding-2B` actual output).
- Text embedding call uses `.process()` instead of `.embed_documents()` (`Qwen3VLEmbedder` API).
- Avoid `HuggingFaceEmbeddings` type annotations for this embedder.

## Delivery and research quality

- After a coherent requested change is implemented and verified, make a thematic commit and push it to the PaperScientist GitHub repository. Inspect the remote first; never force-push or include credentials, private sessions, downloaded corpora or unrelated local work.
- This workspace can have changes predating the current remote history. Use a clean publication worktree based on the current remote branch when necessary; preserve the development checkout and verify the pushed commit.
- Record each completed theme, validation and commit URL in `docs/changes/YYYY-MM-DD.md` using Asia/Shanghai dates. Synchronize that day's entries to https://my.feishu.cn/wiki/Ea6lwgDPBi0jLSkbLJfc6pf7nCe with one date heading and separated thematic paragraphs. Read the existing section first, avoid duplicates, preserve other content, and read back after writing. Missing authorization is a pending sync, never a successful update.
- Preserve the user's manuscript column/page requirements in a layout contract. Do not introduce landscape pages or wider figures just to conceal overflow. Compilation is complete only after the PDF layout gate passes; inspect final-size diagrams for overlap and readability.
- Use the configured research specialist profiles for substantial tasks. Tool/skill isolation must be enforced in binding and dispatch, including nested agents and durable runs. Custom harness failures must not be bypassed by switching tools.
- For relevant empirical work, identify applicable primary-source benchmarks, pin datasets/graders and pre-register the evaluation protocol. Keep synthetic adapter checks, subsets and official benchmark results distinct.
