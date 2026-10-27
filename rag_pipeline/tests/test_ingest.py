import tempfile
import unittest
from pathlib import Path

import ingest
import tests.helpers  # noqa: F401

GOOD = """---
topic: demo_topic
source: https://example.org/demo
last_updated: 2026-06-27
---

## EN

First English paragraph about demo.

## FR

Premier paragraphe en français.
"""


WITH_PIDGIN = GOOD + """
## PCM

Dis na di Pidgin paragraph fo demo.
"""


class IngestTests(unittest.TestCase):
    def kb(self, files):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, text in files.items():
            (Path(folder.name) / name).write_text(text, encoding="utf-8")
        return Path(folder.name)

    def test_real_knowledge_base_loads_with_complete_metadata(self):
        records = ingest.load_markdown_chunks()
        self.assertEqual(len(records), 44)
        topics = {r["metadata"]["topic"] for r in records}
        self.assertEqual(len(topics), 9)
        for r in records:
            for key in ("source_file", "topic", "language", "source_url", "review_date"):
                self.assertTrue(r["metadata"].get(key), f"{r['id']} lacks {key}")
            self.assertIn(r["metadata"]["language"], ("EN", "FR"))
        self.assertEqual(len({r["id"] for r in records}), len(records), "ids must be unique")

    def test_every_topic_has_both_english_and_french(self):
        records = ingest.load_markdown_chunks()
        langs = {}
        for r in records:
            langs.setdefault(r["metadata"]["topic"], set()).add(r["metadata"]["language"])
        self.assertTrue(all(v == {"EN", "FR"} for v in langs.values()), langs)

    def test_good_file_is_accepted(self):
        records = ingest.load_markdown_chunks(self.kb({"01_demo.md": GOOD}))
        self.assertEqual({r["metadata"]["language"] for r in records}, {"EN", "FR"})

    def test_missing_frontmatter_field_stops_ingestion(self):
        bad = GOOD.replace("last_updated: 2026-06-27\n", "")
        with self.assertRaisesRegex(ingest.CorpusError, "last_updated"):
            ingest.load_markdown_chunks(self.kb({"01_demo.md": bad}))

    def test_missing_french_section_stops_ingestion(self):
        bad = GOOD.split("## FR")[0]
        with self.assertRaisesRegex(ingest.CorpusError, "FR"):
            ingest.load_markdown_chunks(self.kb({"01_demo.md": bad}))

    def test_no_frontmatter_at_all_stops_ingestion(self):
        with self.assertRaises(ingest.CorpusError):
            ingest.load_markdown_chunks(self.kb({"01_demo.md": "## EN\n\nhello\n\n## FR\n\nbonjour\n"}))

    def test_readme_and_sources_are_skipped(self):
        records = ingest.load_markdown_chunks(self.kb({"01_demo.md": GOOD, "00_README.md": "# not a topic",
                                                       "sources.md": "# list"}))
        self.assertTrue(all(r["metadata"]["source_file"] == "01_demo.md" for r in records))

    def test_chunks_respect_the_size_limit(self):
        long_text = "\n\n".join(["word " * 100] * 5)
        chunks = ingest.chunk_text(long_text, max_words=180)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.split()) <= 200 for c in chunks))

    def test_counterpart_warning(self):
        recs = [{"metadata": {"source_file": "a.md", "language": "EN"}}] * 2 + \
               [{"metadata": {"source_file": "a.md", "language": "FR"}}] * 3
        self.assertEqual(len(ingest.check_counterparts(recs)), 1)

    def test_pidgin_section_is_optional_and_loaded_when_present(self):
        without = ingest.load_markdown_chunks(self.kb({"01_demo.md": GOOD}))
        self.assertEqual({r["metadata"]["language"] for r in without}, {"EN", "FR"})
        with_pcm = ingest.load_markdown_chunks(self.kb({"01_demo.md": WITH_PIDGIN}))
        self.assertEqual({r["metadata"]["language"] for r in with_pcm}, {"EN", "FR", "PCM"})
        pcm = [r for r in with_pcm if r["metadata"]["language"] == "PCM"][0]
        self.assertEqual(pcm["id"], "01_demo_PCM_0")
        self.assertIn("Pidgin paragraph", pcm["text"])

    def test_missing_pidgin_is_not_a_corpus_error_but_missing_french_still_is(self):
        no_fr = GOOD.split("## FR")[0] + "\n## PCM\n\nPidgin only.\n"
        with self.assertRaises(ingest.CorpusError):
            ingest.load_markdown_chunks(self.kb({"01_demo.md": no_fr}))

    def test_counterpart_warning_only_compares_english_and_french(self):
        records = ingest.load_markdown_chunks(self.kb({"01_demo.md": WITH_PIDGIN}))
        self.assertEqual(ingest.check_counterparts(records), [])


if __name__ == "__main__":
    unittest.main()
