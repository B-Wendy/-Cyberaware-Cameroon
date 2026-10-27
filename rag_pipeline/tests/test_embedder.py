import unittest

import numpy as np

from tests.helpers import build_embedder_and_records
from embedder import is_zero_vector, normalise, tokenize


class EmbedderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder, cls.records = build_embedder_and_records()

    def test_vectors_are_unit_length(self):
        for text in ["how do I spot a phishing SMS", "mot de passe robuste", "ransomware backup"]:
            v = np.array(self.embedder.embed(text))
            self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=6)

    def test_identical_texts_have_similarity_one(self):
        a = np.array(self.embedder.embed("protect my mobile money account"))
        b = np.array(self.embedder.embed("protect my mobile money account"))
        self.assertAlmostEqual(float(a @ b), 1.0, places=6)

    def test_unrelated_texts_have_near_zero_similarity(self):
        a = np.array(self.embedder.embed("phishing sms scam"))
        b = np.array(self.embedder.embed("backup ransomware recovery"))
        self.assertLess(float(a @ b), 0.2)

    def test_out_of_vocabulary_input_gives_zero_vector(self):
        v = self.embedder.embed("zzzqx qqqwv xxyyzz")
        self.assertTrue(is_zero_vector(v))

    def test_empty_input_gives_zero_vector(self):
        self.assertTrue(is_zero_vector(self.embedder.embed("")))

    def test_idf_is_smoothed_formula(self):
        import math
        n = len(self.records)
        word = "phishing"
        df = sum(1 for r in self.records if word in set(tokenize(normalise(r["text"]))))
        self.assertGreater(df, 0)
        self.assertAlmostEqual(self.embedder.idf[word], math.log((n + 1) / (df + 1)) + 1, places=9)

    def test_normalise_lowercases_and_collapses_spaces(self):
        self.assertEqual(normalise("  Hello\n\n  WORLD \t"), "hello world")


if __name__ == "__main__":
    unittest.main()
