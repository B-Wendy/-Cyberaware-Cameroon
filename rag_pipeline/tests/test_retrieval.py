import unittest
from unittest import mock

import rag
from tests.helpers import FakeCollection, build_embedder_and_records


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder, cls.records = build_embedder_and_records()

    def setUp(self):
        self.collection = FakeCollection(self.embedder, self.records)
        self._p1 = mock.patch.object(rag, "get_embedder", lambda: self.embedder)
        self._p2 = mock.patch.object(rag, "get_collection", lambda: self.collection)
        self._p1.start(); self._p2.start()

    def tearDown(self):
        self._p1.stop(); self._p2.stop()

    def test_default_settings_match_dissertation(self):
        self.assertEqual(rag.TOP_K, 4)
        self.assertEqual(rag.TEMPERATURE, 0.2)
        self.assertEqual(rag.MAX_TOKENS, 1000)

    def test_relevant_question_returns_the_right_topic(self):
        hits, used = rag.retrieve("What makes a strong password?", "en")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["meta"]["topic"], "passwords")
        self.assertEqual(used, "EN")

    def test_never_more_than_k_hits_and_sorted_best_first(self):
        hits, _ = rag.retrieve("How do I report a cybercrime to CIRT?", "en", k=4)
        self.assertLessEqual(len(hits), 4)
        sims = [h["similarity"] for h in hits]
        self.assertEqual(sims, sorted(sims, reverse=True))

    def test_every_hit_is_at_or_above_the_threshold(self):
        hits, _ = rag.retrieve("How do I report a cybercrime to CIRT?", "en", threshold=0.10)
        self.assertTrue(all(h["similarity"] >= 0.10 for h in hits))

    def test_a_higher_threshold_discards_weaker_hits(self):
        low, _ = rag.retrieve("How do I report a cybercrime to CIRT?", "en", threshold=0.0)
        high, _ = rag.retrieve("How do I report a cybercrime to CIRT?", "en", threshold=0.25)
        self.assertGreater(len(low), len(high))

    def test_french_question_retrieves_french_passages(self):
        hits, used = rag.retrieve("Qu'est-ce qu'un mot de passe robuste ?", "fr")
        self.assertTrue(hits)
        self.assertEqual(used, "FR")
        self.assertTrue(all(h["meta"]["language"] == "FR" for h in hits))

    def test_pidgin_question_searches_english_passages(self):
        hits, used = rag.retrieve("Wetin make password strong?", "pidgin")
        self.assertTrue(hits)
        self.assertEqual(used, "EN")
        self.assertTrue(all(h["meta"]["language"] == "EN" for h in hits))

    def test_language_filter_is_sent_to_the_vector_store(self):
        rag.retrieve("Qu'est-ce qu'un mot de passe robuste ?", "fr")
        self.assertEqual(self.collection.queries[0]["where"], {"language": "FR"})

    def test_french_falls_back_to_english_when_french_has_nothing(self):
        # Remove every French passage: a French-language question must fall back to English.
        english_only = [r for r in self.records if r["metadata"]["language"] == "EN"]
        self.collection = FakeCollection(self.embedder, english_only)
        hits, used = rag.retrieve("What makes a strong password?", "fr")
        self.assertTrue(hits)
        self.assertEqual(used, "EN")
        self.assertEqual([q["where"]["language"] for q in self.collection.queries], ["FR", "EN"])

    def test_unknown_words_give_zero_vector_and_no_search(self):
        hits, used = rag.retrieve("zzzqx qqqwv", "en")
        self.assertEqual((hits, used), ([], None))
        self.assertEqual(self.collection.queries, [])     # the store was never queried

    def test_question_of_only_common_words_is_treated_as_empty(self):
        hits, _ = rag.retrieve("what is the of and", "en")
        self.assertEqual(hits, [])

    def test_off_topic_question_is_rejected(self):
        for q in ["What is the capital of France?", "recipe for jollof rice", "Who won the football match yesterday?"]:
            hits, _ = rag.retrieve(q, "en")
            self.assertEqual(hits, [], q)

    def test_filtered_search_error_falls_back_to_search_then_filter(self):
        real_query = self.collection.query
        calls = {"n": 0}

        def flaky(query_embeddings, n_results, where=None, include=None):
            calls["n"] += 1
            if where is not None:
                raise RuntimeError("filtered search not available")
            return real_query(query_embeddings, n_results, None, include)

        self.collection.query = flaky
        hits, _ = rag.retrieve("What makes a strong password?", "en")
        self.assertTrue(hits)
        self.assertTrue(all(h["meta"]["language"] == "EN" for h in hits))
        self.assertGreaterEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()


class PidginPassageTests(unittest.TestCase):
    """When a topic has a Pidgin ("PCM") passage, Pidgin questions use it first;
    topics without one fall back to the English passage."""

    PCM_PASSWORD = {
        "id": "demo_PCM_0",
        "text": ("Password na di first door fo yu account. Strong password mus get at least 12 characters "
                 "wit big letter, small letter, number and symbol. No use di same password fo plenti accounts."),
        "metadata": {"source_file": "04_passwords.md", "topic": "passwords", "language": "PCM",
                     "source_url": "https://cirt.cm/", "review_date": "2026-10-13"},
    }

    @classmethod
    def setUpClass(cls):
        import ingest
        from embedder import TFIDFEmbedder, normalise
        import contextlib, io
        records = ingest.load_markdown_chunks() + [cls.PCM_PASSWORD]
        cls.embedder = TFIDFEmbedder()
        with contextlib.redirect_stdout(io.StringIO()):
            cls.embedder.fit([normalise(r["text"]) for r in records])
        cls.records = records

    def setUp(self):
        self.collection = FakeCollection(self.embedder, self.records)
        self._p1 = mock.patch.object(rag, "get_embedder", lambda: self.embedder)
        self._p2 = mock.patch.object(rag, "get_collection", lambda: self.collection)
        self._p1.start(); self._p2.start()

    def tearDown(self):
        self._p1.stop(); self._p2.stop()

    def test_pidgin_question_prefers_the_pidgin_passage(self):
        hits, used = rag.retrieve("Wetin make password strong?", "pidgin")
        self.assertEqual(used, "PCM")
        self.assertTrue(all(h["meta"]["language"] == "PCM" for h in hits))
        self.assertEqual(self.collection.queries[0]["where"], {"language": "PCM"})

    def test_pidgin_question_on_a_topic_without_pidgin_falls_back_to_english(self):
        hits, used = rag.retrieve("How I go report cybercrime to CIRT?", "pidgin")
        self.assertEqual(used, "EN")
        self.assertTrue(hits)
        self.assertTrue(all(h["meta"]["language"] == "EN" for h in hits))

    def test_english_and_french_questions_never_see_pidgin_passages(self):
        for lang, q in (("en", "What makes a strong password?"), ("fr", "Qu'est-ce qu'un mot de passe robuste ?")):
            hits, _ = rag.retrieve(q, lang)
            self.assertTrue(all(h["meta"]["language"] != "PCM" for h in hits))

    def test_context_sent_to_the_model_names_the_pidgin_language(self):
        hits, _ = rag.retrieve("Wetin make password strong?", "pidgin")
        self.assertIn("Language: PCM", rag.build_context(hits))
