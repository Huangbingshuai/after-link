"""Read relevant source sections from the Neo4j knowledge graph."""

import sys

from app.clients.neo4j_utils import search_document_chunks
from app.core.logger import logger
from app.utils.task_utils import add_done_task, add_running_task


def node_query_kg(state):
    """Return graph-matched source chunks; failures degrade to an empty result."""
    node_name = sys._getframe().f_code.co_name
    session_id = state.get("session_id", "")
    is_stream = state.get("is_stream")
    add_running_task(session_id, node_name, is_stream)
    try:
        query = (state.get("rewritten_query") or state.get("original_query") or "").strip()
        if not query:
            return {"kg_chunks": []}

        item_names = state.get("item_names") or []
        chunks = search_document_chunks(query, item_names=item_names, limit=10)
        logger.info(f"Neo4j图谱检索完成：查询切片数={len(chunks)}，产品过滤数={len(item_names)}")
        return {"kg_chunks": chunks}
    except Exception as error:
        logger.warning(f"Neo4j图谱检索不可用，本轮继续使用其他检索源：{error}", exc_info=True)
        return {"kg_chunks": []}
    finally:
        add_done_task(session_id, node_name, is_stream)
