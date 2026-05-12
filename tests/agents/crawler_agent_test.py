# FILE: tests/agents/crawler_agent_test.py | PURPOSE: Unit tests for crawler agent helpers
import unittest
from src.agents.crawler_agent import build_crawler_queries, normalize_crawler_items

class TestCrawlerAgent(unittest.TestCase):
    def test_build_crawler_queries_returns_five(self):
        queries = build_crawler_queries()
        self.assertEqual(len(queries), 5)
        self.assertTrue(all(isinstance(q, str) and len(q) > 0 for q in queries))

    def test_normalize_crawler_items_valid(self):
        items = normalize_crawler_items("run-1", "query", [{
            "title": "Royal Enfield Guerrilla 450 launched",
            "url": "https://example.com/story",
            "published_at": "2026-01-01T00:00:00.000Z",
            "snippet": "Launch details and price announced.",
        }])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_id"], "example.com")
        self.assertEqual(items[0]["status"], "pending")
        self.assertEqual(len(items[0]["url_hash"]), 64)

if __name__ == '__main__':
    unittest.main()
