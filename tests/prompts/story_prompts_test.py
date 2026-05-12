import unittest

from src.prompts.story_prompts import build_story_prompt


class StoryPromptsTest(unittest.TestCase):
    def test_build_story_prompt_includes_cluster_context_and_dedupes_sources(self):
        cluster = {
            "canonical_topic": "KTM 390 Adventure update",
            "story_type": "update",
        }
        items = [
            {
                "title": "KTM 390 Adventure update for India",
                "snippet": "KTM could bring revised touring features and better pricing in India.",
                "published_at": "2026-04-24",
                "url": "https://example.com/ktm-390-adventure-update",
            },
            {
                "title": "KTM 390 Adventure update for India",
                "snippet": "KTM could bring revised touring features and better pricing in India.",
                "published_at": "2026-04-24",
                "url": "https://example.com/ktm-390-adventure-update",
            },
        ]

        prompt = build_story_prompt(cluster, items)

        self.assertIn("Canonical topic: KTM 390 Adventure update", prompt)
        self.assertIn("Cluster story type hint: update", prompt)
        self.assertEqual(prompt.count("Source 1 title:"), 1)
        self.assertNotIn("Source 2 title:", prompt)


if __name__ == "__main__":
    unittest.main()
