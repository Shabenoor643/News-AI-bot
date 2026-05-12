# FILE: tests/utils/fingerprint_test.py | PURPOSE: Unit tests for fingerprint utilities
import unittest
from src.utils.fingerprint import generate_fingerprint, jaccard_similarity

class TestFingerprint(unittest.TestCase):
    def test_generate_fingerprint_removes_stop_words(self):
        fingerprint = generate_fingerprint("The new Royal Enfield Himalayan motorcycle launch in India")
        self.assertFalse("the" in fingerprint)
        self.assertFalse("new" in fingerprint)
        self.assertTrue("royal" in fingerprint)
        self.assertTrue("himalayan" in fingerprint)

    def test_jaccard_similarity_extremes(self):
        set_a = {"royal", "enfield"}
        set_b = {"royal", "enfield"}
        set_c = {"yamaha"}
        self.assertEqual(jaccard_similarity(set_a, set_b), 1.0)
        self.assertEqual(jaccard_similarity(set_a, set_c), 0.0)

    def test_similar_titles_cross_threshold(self):
        set_a = generate_fingerprint("Royal Enfield Guerrilla 450 launch price India")
        set_b = generate_fingerprint("Royal Enfield Guerrilla 450 launched in India with price")
        self.assertTrue(jaccard_similarity(set_a, set_b) >= 0.5)

if __name__ == '__main__':
    unittest.main()
