import unittest

from src.utils.article_quality import assess_article_quality, sanitize_article_markdown

class ArticleQualityTest(unittest.TestCase):
    def test_sanitize_article_markdown_normalizes_expected_headings(self):
        article = """
        # Hero Xtreme 250R update

        Something big is coming for riders waiting for a sharper street bike.
        The Hero Xtreme 250R now matters because pricing could shift the segment.

        ## What is new
        Hero has revised the trim and pricing details for buyers in India.

        ## Features
        The bike gets updated body panels and better connected features.

        ## Performance
        Output changes remain modest but the bike should feel sharper in traffic.

        ## Price
        It should stay competitive against similarly priced 250cc rivals.

        ## Should you care
        It looks best for daily commuters who want something more exciting.
        """

        sanitized = sanitize_article_markdown(article)

        self.assertIn("## What's new", sanitized)
        self.assertIn("## Design / Features", sanitized)
        self.assertIn("## Engine / Performance", sanitized)
        self.assertIn("## Price & Positioning", sanitized)
        self.assertIn("## Should You Care?", sanitized)
        self.assertNotIn("# Hero Xtreme 250R update", sanitized)

    def test_assess_article_quality_flags_structured_buyer_focused_article(self):
        article = """
        The TVS Apache RTR 310 is finally looking like a stronger everyday performance option.
        That matters because buyers care more about value than headline specs alone.

        ## What's new
        TVS has updated the trim mix, feature list, and city-focused positioning.
        Buyers now get better equipment without stretching far beyond the segment.

        ## Design / Features
        The sharper front end and cleaner graphics make it look more premium.
        Riders also get connected features and practical urban touches.

        ## Engine / Performance
        The engine still aims for a quick, flexible character on busy roads.
        It should feel lively enough for weekend highway runs as well.

        ## Price & Positioning
        Value for money is stronger because the feature list feels less compromised.
        It sits against KTM and Yamaha rivals that ask buyers to choose differently.

        ## Should You Care?
        This looks best for daily commuters who still want some weekend excitement.
        It is not ideal for absolute beginners who want a calmer first bike.
        """

        quality = assess_article_quality(article)

        self.assertEqual(quality["heading_hits"], 5)
        self.assertTrue(quality["buyer_intent_present"])
        self.assertIsInstance(quality["eligible"], bool)
        self.assertGreater(quality["score"], 0)
