"""Shared Neo4j driver and idempotent document graph operations."""

import hashlib
import os
import re
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

_neo4j_driver = None


def get_neo4j_driver():
    """Return the process-wide Neo4j driver, validating its configuration."""
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = (os.getenv("NEO4J_URI") or "").strip()
        username = (os.getenv("NEO4J_USERNAME") or "").strip()
        password = (os.getenv("NEO4J_PASSWORD") or "").strip()
        if not uri or not username or not password:
            raise RuntimeError("Neo4j配置缺失：请设置 NEO4J_URI、NEO4J_USERNAME 和 NEO4J_PASSWORD")
        _neo4j_driver = GraphDatabase.driver(uri, auth=(username, password))
    return _neo4j_driver


def _stable_id(*parts: str) -> str:
    value = "\x1f".join(str(part or "").strip() for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def upsert_document_chunks(chunks: list[dict[str, Any]], item_name: str, file_title: str) -> int:
    """Upsert a product → document → chunk graph without removing existing data."""
    product_name = (item_name or "").strip()
    document_title = (file_title or "").strip()
    if not product_name or not document_title:
        raise ValueError("Neo4j导入需要非空的 item_name 和 file_title")
    if not chunks:
        raise ValueError("Neo4j导入需要至少一个文档切片")

    document_id = _stable_id(product_name.casefold(), document_title.casefold())
    rows = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        content = (chunk.get("content") or "").strip()
        if not content:
            continue
        title = (chunk.get("title") or "").strip()
        part = chunk.get("part", index)
        chunk_id = (chunk.get("chunk_id") or "")
        graph_id = _stable_id(document_id, str(part), title, content)
        rows.append({
            "id": graph_id,
            "chunk_id": str(chunk_id) if chunk_id else graph_id,
            "title": title,
            "parent_title": (chunk.get("parent_title") or "").strip(),
            "content": content,
            "part": int(part) if str(part).lstrip("-+").isdigit() else index,
            "file_title": (chunk.get("file_title") or document_title).strip(),
        })
    if not rows:
        raise ValueError("Neo4j导入未找到有效的切片正文")

    query = """
    MERGE (product:Product {name: $item_name})
    MERGE (document:Document {id: $document_id})
    SET document.title = $file_title,
        document.item_name = $item_name,
        document.updated_at = datetime()
    MERGE (product)-[:HAS_DOCUMENT]->(document)
    WITH product, document
    OPTIONAL MATCH (document)-[:HAS_CHUNK]->(old_chunk:Chunk)
    WITH product, document, collect(old_chunk) AS old_chunks
    FOREACH (old_chunk IN old_chunks | SET old_chunk.active = false)
    WITH product, document
    UNWIND $chunks AS row
    MERGE (chunk:Chunk {id: row.id})
    SET chunk.chunk_id = row.chunk_id,
        chunk.title = row.title,
        chunk.parent_title = row.parent_title,
        chunk.content = row.content,
        chunk.part = row.part,
        chunk.file_title = row.file_title,
        chunk.item_name = $item_name,
        chunk.active = true
    MERGE (document)-[:HAS_CHUNK]->(chunk)
    MERGE (chunk)-[:ABOUT_PRODUCT]->(product)
    RETURN count(DISTINCT chunk) AS chunks_written
    """

    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.execute_write(
            lambda tx: tx.run(
                query,
                chunks=rows,
                item_name=product_name,
                file_title=document_title,
                document_id=document_id,
            ).single()["chunks_written"]
        )
    return int(result)


_STOP_WORDS = {
    "怎么", "如何", "什么", "请问", "一下", "这个", "那个", "里面", "具体", "操作",
    "是否", "可以", "需要", "以及", "并且", "和", "是", "的", "在", "了", "吗", "么",
}


def build_graph_search_terms(query: str) -> list[str]:
    """Extract useful Latin/numeric terms and Chinese bigrams for substring matching."""
    source = (query or "").strip().lower()
    terms = []
    seen = set()
    for match in re.finditer(r"[a-z0-9][a-z0-9._/+:-]*|[\u4e00-\u9fff]+", source):
        token = match.group(0)
        candidates = [token] if re.fullmatch(r"[a-z0-9][a-z0-9._/+:-]*", token) else (
            [token] if len(token) <= 4 else [token[i:i + 2] for i in range(len(token) - 1)]
        )
        for candidate in candidates:
            if candidate in _STOP_WORDS or len(candidate) < 2 or candidate in seen:
                continue
            seen.add(candidate)
            terms.append(candidate)
    return terms[:40]


def search_document_chunks(query: str, item_names: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Find source chunks by lexical term overlap, optionally scoped to products."""
    terms = build_graph_search_terms(query)
    if not terms:
        return []

    query_text = """
    MATCH (chunk:Chunk)
    WHERE coalesce(chunk.active, true) = true
      AND ($item_names = [] OR chunk.item_name IN $item_names)
    WITH chunk,
         reduce(score = 0, term IN $terms |
           score + CASE WHEN toLower(chunk.content) CONTAINS term
                         OR toLower(coalesce(chunk.title, '')) CONTAINS term
                         OR toLower(coalesce(chunk.parent_title, '')) CONTAINS term
                    THEN 1 ELSE 0 END) AS lexical_score
    WHERE lexical_score > 0
    RETURN chunk.chunk_id AS chunk_id,
           chunk.content AS content,
           chunk.title AS title,
           chunk.parent_title AS parent_title,
           chunk.file_title AS file_title,
           chunk.item_name AS item_name,
           lexical_score AS score
    ORDER BY lexical_score DESC, chunk.file_title, chunk.part
    LIMIT $limit
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        records = session.execute_read(
            lambda tx: list(tx.run(
                query_text,
                item_names=[str(name).strip() for name in (item_names or []) if str(name).strip()],
                terms=terms,
                limit=max(1, min(int(limit), 20)),
            ))
        )
    return [record.data() for record in records]


def close_neo4j_driver() -> None:
    """Close the cached Neo4j driver, mainly for graceful process shutdown/tests."""
    global _neo4j_driver
    if _neo4j_driver is not None:
        _neo4j_driver.close()
        _neo4j_driver = None
