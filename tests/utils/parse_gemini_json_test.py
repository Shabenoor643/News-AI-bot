# FILE: tests/utils/parse_gemini_json_test.py | PURPOSE: Unit tests for Gemini JSON parsing utility
import unittest
from src.utils.parse_gemini_json import parse_gemini_json
from src.utils.error_handler import GeminiParseError

class TestParseGeminiJSON(unittest.TestCase):
    def test_parse_gemini_json_strips_markdown_fences(self):
        parsed = parse_gemini_json('```json\n{"title":"Test"}\n```', "test")
        self.assertEqual(parsed, {"title": "Test"})

    def test_parse_gemini_json_returns_object(self):
        parsed = parse_gemini_json('{"tags":["one","two"]}', "test")
        self.assertEqual(parsed, {"tags": ["one", "two"]})

    def test_parse_gemini_json_throws_error(self):
        with self.assertRaises(GeminiParseError):
            parse_gemini_json("not-json", "test")

if __name__ == '__main__':
    unittest.main()
