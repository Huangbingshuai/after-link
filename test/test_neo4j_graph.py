"""Offline regression tests for the non-destructive Neo4j document graph."""

import unittest
from unittest.mock import patch

from app.clients import neo4j_utils


class _Record(dict):
    def data(self):
        return dict(self)


class _Result:
    def __init__(self, records=None):
        self.records = records or []

    def single(self):
        return _Record(chunks_written=len(self.records))

    def __iter__(self):
        return iter(self.records)


class _Transaction:
    def __init__(self, driver):
        self.driver = driver

    def run(self, query, **params):
        self.driver.queries.append(query)
        if "UNWIND $chunks AS row" in query:
            document_id = params["document_id"]
            for stored in self.driver.chunks.values():
                if stored["document_id"] == document_id:
                    stored["active"] = False
            for row in params["chunks"]:
                self.driver.chunks[(document_id, row["id"])] = {
                    **row,
                    "document_id": document_id,
                    "item_name": params["item_name"],
                    "active": True,
                }
            return _Result([{} for _ in params["chunks"]])

        terms = params["terms"]
        item_names = params["item_names"]
        matches = []
        for stored in self.driver.chunks.values():
            if not stored["active"] or (item_names and stored["item_name"] not in item_names):
                continue
            searchable = " ".join((stored.get("content", ""), stored.get("title", ""))).lower()
            score = sum(term in searchable for term in terms)
            if score:
                matches.append(_Record(
                    chunk_id=stored["chunk_id"],
                    content=stored["content"],
                    title=stored["title"],
                    parent_title=stored["parent_title"],
                    file_title=stored["file_title"],
                    item_name=stored["item_name"],
                    score=score,
                ))
        return _Result(matches)


class _Session:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute_write(self, callback):
        return callback(_Transaction(self.driver))

    def execute_read(self, callback):
        return callback(_Transaction(self.driver))


class _Driver:
    def __init__(self):
        self.chunks = {}
        self.queries = []

    def session(self):
        return _Session(self)


class Neo4jGraphTests(unittest.TestCase):
    def test_reimport_marks_old_sections_inactive_and_search_returns_current_text(self):
        driver = _Driver()
        with patch.object(neo4j_utils, "get_neo4j_driver", return_value=driver):
            neo4j_utils.upsert_document_chunks(
                [{"title": "## Command", "content": "obsolete command parameter", "part": 1}],
                "Device A",
                "Manual A",
            )
            neo4j_utils.upsert_document_chunks(
                [{"title": "## Command", "content": "updated command parameter", "part": 1}],
                "Device A",
                "Manual A",
            )

            query = driver.queries[-1]
            self.assertIn("SET old_chunk.active = false", query)
            self.assertNotIn("DELETE", query.upper())
            self.assertEqual(sum(chunk["active"] for chunk in driver.chunks.values()), 1)

            current = neo4j_utils.search_document_chunks("updated command parameter", ["Device A"])
            stale = neo4j_utils.search_document_chunks("obsolete", ["Device A"])

        self.assertEqual(len(current), 1)
        self.assertIn("updated", current[0]["content"])
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
