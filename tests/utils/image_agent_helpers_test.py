import unittest

from src.utils.bike_name import extract_bike_name

class ImageAgentHelpersTest(unittest.TestCase):
    def test_extract_bike_name_prefers_known_brand_pattern(self):
        draft = {
            "title": "Honda CB350 update brings new trim and sharper value",
            "body": "Honda says the CB350 stays aimed at relaxed city and highway buyers.",
        }

        self.assertEqual(extract_bike_name(draft), "Honda CB350")

    def test_extract_bike_name_falls_back_to_title_prefix(self):
        draft = {
            "title": "Upcoming naked bike could shake up the 250cc class: what to expect",
            "body": "",
        }

        self.assertEqual(extract_bike_name(draft), "Upcoming naked bike could shake")
