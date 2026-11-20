# Unified Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve knowledge chat and document import from one polished, navigable workspace while preserving both existing backend workflows.

**Architecture:** Add a unified workspace page served at `/` by the query API on port 8003. The page calls query endpoints on its own origin and import endpoints on the same hostname at port 8002; both existing FastAPI processes and their data workflows remain separate. Existing `/chat.html` and `/import.html` routes remain available.

**Tech Stack:** Existing FastAPI, static HTML/CSS/JavaScript, browser `fetch`, `EventSource`, local Conda Python environment, Docker Compose service containers.

**Spec:** `docs/superpowers/specs/2026-11-20-unified-workspace-design.md`

## Global Constraints

- Query API listens only on `127.0.0.1:8003`; import API listens only on `127.0.0.1:8002`.
- Preserve query SSE events, session history, clear-history behavior, and existing API payloads.
- When a previous query stream closes, remove only its own queue instance so it cannot delete a replacement queue for the same session.
- Preserve import multipart field `files`, `task_ids` result, task status values, and `done_list` / `running_list` fields.
- Retain `/chat.html` and `/import.html` as working legacy routes.
- Keep navigation switches in-page so unsent chat and active import task cards remain visible.
- Use the approved mineral gray-green palette, restrained forest-green accents, source-index styling, keyboard focus, and reduced-motion behavior.
- Do not change graph workflows, database schemas, or persistent Docker volumes.
- The user later authorized full manual end-to-end testing with one PDF from `doc/`, one MinerU import, and a small number of DeepSeek queries. Do not reset data or remove the test document/vector records. Avoid unrelated destructive legacy test scripts.

## Review Focus

- Import API unavailable or CORS blocked: show a clear import-specific connection error and leave chat usable. Check the composed import origin and read-only CORS response headers without stopping services.
- Query stream disconnects or returns malformed event data: show a recoverable error and re-enable the composer; inspect event handling without sending paid model requests.
- A user sends another query as a previous EventSource closes: preserve the new session queue; inspect instance-safe cleanup without sending paid model requests.
- Empty chat history and a fresh session: show a useful first-use state and a working composer.
- Multiple selected import files: create and track one task per file without cross-wiring progress or logs.
- Narrow viewport and keyboard navigation: allow switching workflows and operating upload/chat controls without horizontal overflow or lost focus.

---

### Task 1: Build the unified workspace page

**Files:**
- Create: `app/query_process/page/workspace.html`

**Interfaces:**
- Consumes: query routes `/health`, `/query`, `/stream/{session_id}`, `/history/{session_id}`, and `DELETE /history/{session_id}` on `location.origin`; import routes `/upload` and `/status/{task_id}` on `http(s)://{location.hostname}:8002`.
- Produces: one static page containing the sidebar shell, chat view, and import view; navigation switches visibility without destroying either view's state.

- [ ] **Step 1: Create the workspace structure and visual system**
  Add the left navigation, restrained header/status area, query workspace, and import workspace. Use the approved palette and source-index signature; make the layout responsive, keyboard reachable, and respectful of `prefers-reduced-motion`.
- [ ] **Step 2: Implement query interactions**
  Keep one `kb_session_id` in localStorage, load history on startup, post `{query, session_id, is_stream:true}` to `/query`, consume `progress`, `delta`, `final`, `final_answer`, and `error` SSE events from `/stream/{session_id}`, and preserve clear-history behavior.
- [ ] **Step 3: Implement import interactions**
  Accept multiple PDF/Markdown files and drag/drop; upload each file with multipart field `files` to port 8002 `/upload`; poll `/status/{task_id}` every two seconds until `completed` or `failed`; display per-file state and expandable node logs.
- [ ] **Step 4: Handle empty, loading, and failure states**
  Keep the unaffected workflow available when one API is unavailable; use specific status copy, stop polling after terminal status, and re-enable controls after errors.

### Task 2: Serve the workspace at the query API root

**Files:**
- Modify: `app/query_process/api/query_service.py`

**Interfaces:**
- Consumes: `app/query_process/page/workspace.html` from Task 1.
- Produces: `GET /` returning the unified workspace while retaining `/chat.html`, `/health`, query, stream, and history routes unchanged.

- [ ] **Step 1: Add the root page route**
  Resolve the workspace path from the module location and return it with `FileResponse`; keep existing `/chat.html` route behavior intact.
- [ ] **Step 2: Manually verify routes**
  Confirm `GET /` returns the workspace HTML, `GET /chat.html` still returns the legacy chat page, and `GET /health` returns `{"ok":true}` on port 8003.

### Task 3: Repair the standalone import page's API origin

**Files:**
- Modify: `app/import_process/page/import.html`

**Interfaces:**
- Consumes: existing import API on port 8002.
- Produces: legacy `/import.html` works when served by the import API without contacting the stale port 8000.

- [ ] **Step 1: Derive the import API origin from the current page host**
  Set the import page API base to `window.location.origin` (the page is served on port 8002); leave request payloads and response handling unchanged.
- [ ] **Step 2: Manually verify the standalone page**
  Confirm `GET http://127.0.0.1:8002/import.html` renders and its JavaScript builds `/upload` and `/status/{task_id}` URLs against port 8002.

### Task 4: Make SSE queue cleanup safe for consecutive queries

**Files:**
- Modify: `app/utils/sse_utils.py`

**Interfaces:**
- Consumes: the session ID and the exact queue instance captured by `sse_generator`.
- Produces: `remove_sse_queue(session_id, expected_queue)` deletes the registry entry only when it still points to that queue; a replacement queue remains registered.

- [ ] **Step 1: Synchronize queue registry access**
  Protect create/get/remove operations with one `threading.Lock` so checking a queue identity and removing it is atomic with respect to replacement.
- [ ] **Step 2: Bind stream cleanup to its captured queue**
  Pass the local `stream_queue` to cleanup from `sse_generator`'s `finally` block. Do not change event names or payloads.
- [ ] **Step 3: Review the replacement-queue sequence**
  Manually inspect the sequence where a new queue is installed before an old generator finishes; verify the old queue identity cannot remove the new entry. Do not add or run automated tests.

### Task 5: Verify the running workspace with the user-authorized sample manual

**Files:**
- No additional files.

**Interfaces:**
- Consumes: the workspace and routes from Tasks 1–3 plus running Compose services.
- Produces: confirmed health/page routes, a completed single-document import, a manual-backed answer, and persisted history.

- [x] **Step 1: Check local service health**
  Run `docker compose ps`, `curl -fsS http://127.0.0.1:8003/health`, `curl -fsS http://127.0.0.1:9000/minio/health/live`, and `curl -fsS http://127.0.0.1:9091/healthz` after Milvus reports ready.
- [x] **Step 2: Inspect both page modes in the browser**
  Open `http://127.0.0.1:8003/` and inspect chat/import navigation, empty state, and the completed response.
- [x] **Step 3: Import and query the authorized sample**
  Import only `doc/H3C LA2608室内无线网关 用户手册-6W100-整本手册.pdf`; confirm terminal task status and Milvus insertion; ask a product-specific query and confirm history survives page reload.

### Task 6: Prevent duplicate clarification answers in Mongo history

**Files:**
- Modify: `app/query_process/agent/nodes/node_item_name_confirm.py`

**Interfaces:**
- Consumes: an answer produced by the item-name clarification branch.
- Produces: one user history record and one assistant history record, with the assistant record written by `node_answer_output` only.

- [x] **Step 1: Remove the duplicate assistant write**
  Keep `step_7_write_history` updating the user message and leave assistant persistence to `node_answer_output.step_4_write_history`.
- [x] **Step 2: Verify without modifying existing history**
  Inspect the source write paths and make a fresh clarification query only if needed; do not delete or rewrite existing Mongo history.
