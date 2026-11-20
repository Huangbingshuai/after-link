"""Persist imported documents and sections in the Neo4j knowledge graph."""

import sys

from app.clients.neo4j_utils import upsert_document_chunks
from app.core.logger import logger
from app.utils.task_utils import add_done_task, add_running_task


def node_import_kg(state):
    """Idempotently write product, document, and source-chunk graph records."""
    task_id = state.get("task_id", "")
    node_name = sys._getframe().f_code.co_name
    add_running_task(task_id, node_name)
    try:
        chunks = state.get("chunks") or []
        item_name = (state.get("item_name") or "").strip()
        if not item_name and chunks:
            item_name = (chunks[0].get("item_name") or "").strip()
        file_title = (state.get("file_title") or "").strip()
        written = upsert_document_chunks(chunks, item_name, file_title)
        logger.info(f"Neo4j图谱导入完成：产品={item_name}，文档={file_title}，切片={written}")
        state["kg_import_count"] = written
        state.pop("kg_import_error", None)
    except Exception as error:
        state["kg_import_error"] = str(error)
        logger.error(f"Neo4j图谱导入失败：{error}", exc_info=True)
        # The import job must report a failure instead of claiming the graph is current.
        raise
    finally:
        add_done_task(task_id, node_name)
    return state
