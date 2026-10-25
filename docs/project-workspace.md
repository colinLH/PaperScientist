# Projects, blank chats and local source folders

Clicking **新聊天** opens the most recently updated unused root chat in the selected project. The same operation is used by the sidebar, the top-level button, empty forks, first-page initialization and `POST /api/sessions`. SQLite serializes selection and insertion so concurrent requests do not create duplicate blank chats. Existing duplicate chats are preserved.

A reusable chat has no messages, attachments, files, child agents or durable run records and is not archived/deleted. An unsent text draft stays in the composer when the current blank chat is reused. Once a chat has content, new chat creates or opens a different blank chat. Other projects and users remain separate.

**新建项目** opens a keyboard-accessible dialog with a project name and an optional source folder. The picker browses directories on the computer running this local service, supports drive selection, parent navigation and an absolute path, and does not upload an entire directory. Omit the folder to create an ordinary project. Paths are validated and saved in project state; hovering over the project breadcrumb shows the binding after reload/restart.

`POST /api/projects` accepts `{ "name": "My research", "folder_path": null }` (or an existing absolute directory). Project listings include `folder_path`. Local directory browsing and folder binding reject non-local clients and cross-site requests.

Bound source folders are available on demand through the existing `list_files` and `read_file` tools with `scope="project"`. They are read-only source material: generated files and edits remain in each session's isolated workspace. Existing tool allowlists still apply, isolated reviewers cannot read the folder, and resolved paths cannot escape the bound root. Deleting a project never deletes the selected source directory. This binding is not an operating-system sandbox for separately enabled Python execution.

Validation includes concurrent creation, empty/nonempty/archived chats, queued runs, unsent drafts, folder validation and persistence, cross-site denial, read boundaries, and preservation of source files when deleting a project. Browser checks cover unbound/bound creation, repeated new-chat clicks and page reload.
