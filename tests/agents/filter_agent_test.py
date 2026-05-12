# FILE: tests/agents/filter_agent_test.py | PURPOSE: Unit tests for filter agent scoring
import unittest
import asyncio
from src.db.database import init_db
from src.agents.filter_agent import run_filter_agent, score_raw_item

class TestFilterAgent(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_items_with_motorcycle_keywords_score_high(self):
        item = {
            "item_id": "test-filter-1",
            "title": "Royal Enfield launches new adventure motorcycle",
            "snippet": "The new bike price and specs for India are now official.",
            "language": "en",
        }
        self.assertTrue(score_raw_item(item) >= 0.6)

    async def test_items_below_threshold_excluded(self):
        item = {
            "item_id": "test-filter-3",
            "title": "Stock market update for tech companies",
            "snippet": "Quarterly earnings rose sharply.",
            "language": "en",
        }
        filtered = await run_filter_agent([item])
        self.assertEqual(len(filtered), 0)

    def test_items_with_sponsored_penalized(self):
        sponsored_item = {
            "item_id": "test-filter-2",
            "title": "Sponsored Royal Enfield review",
            "snippet": "A bike review for Indian riders.",
            "language": "en",
        }
        organic_item = {**sponsored_item, "title": "Royal Enfield review"}
        
        self.assertTrue(score_raw_item(sponsored_item) < score_raw_item(organic_item))

if __name__ == '__main__':
    unittest.main()
