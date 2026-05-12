import unittest

from src.prompts.image_prompts import build_image_search_queries


class ImagePromptsTest(unittest.TestCase):
    def test_build_image_search_queries_returns_primary_and_fallback_queries(self):
        queries = build_image_search_queries("Honda CB350")

        self.assertEqual(queries[0], "Honda CB350 official image side view")
        self.assertIn("official", queries[1])
        self.assertIn("profile", queries[1])
        self.assertEqual(len(queries), 2)


if __name__ == "__main__":
    unittest.main()
