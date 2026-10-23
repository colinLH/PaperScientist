# Original implementation

These files preserve the previous fixed literature-collection workflow and environment for comparison. The active entrypoints are `collector.py`, `web/app.py` and the `paperscientist` package. The archived scripts depend on the old import layout and are reference sources, not supported server entrypoints.

Old `memory/`, `checkpoints.db`, `web/chat_sessions/`, search/MySQL helpers, and RL/RAG learning materials are left intact. New state is written to `.paperscientist/research.db` and isolated session workspaces. Use `python -m paperscientist.migrate --help` to explicitly import old chat histories without deleting the originals.
