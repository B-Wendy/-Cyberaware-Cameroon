import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import tests.helpers  # noqa: F401
from config import MAX_QUESTION_CHARS, TEMPLATE_PATH

HTML = TEMPLATE_PATH.read_text(encoding="utf-8")
SCRIPT = re.findall(r"<script>(.*?)</script>", HTML, re.S)[-1]


class FrontEndStaticChecks(unittest.TestCase):
    def test_javascript_has_no_syntax_errors(self):
        # The pre-deployment check from the dissertation (defect D01).
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "page.js"
            path.write_text(SCRIPT, encoding="utf-8")
            result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_onclick_function_exists(self):
        called = set(re.findall(r"onclick=['\"]\s*([A-Za-z_]\w*)\s*\(", HTML))
        called |= set(re.findall(r"onclick='\s*([A-Za-z_]\w*)\s*\(", SCRIPT))
        called |= set(re.findall(r"onclick=\\?['\"]\s*([A-Za-z_]\w*)\s*\(", SCRIPT))
        defined = set(re.findall(r"function\s+([A-Za-z_]\w*)\s*\(", SCRIPT))
        self.assertEqual(sorted(called - defined), [], "buttons that call a function that does not exist")

    def test_no_entitlement_flag_in_browser_storage(self):
        code = re.sub(r"/\*.*?\*/", "", SCRIPT, flags=re.S)           # ignore comments
        self.assertIsNone(re.search(r"\bpremium\b\s*=", code), "a 'premium' variable is back")
        self.assertIsNone(re.search(r"!\s*premium\b|&&\s*premium\b|\bpremium\s*\?", code))
        self.assertNotIn('"cap"', code)
        self.assertNotIn('"cad"', code)
        # The only things stored in the browser are the two signed tokens.
        keys = set(re.findall(r'ls(?:Get|Set)\("([^"]+)"', code))
        self.assertEqual(keys, {"cac_token", "cac_prog"})

    def test_lessons_are_not_embedded_in_the_page(self):
        for needle in ("quiz:[", "sc:{type", "Mbiydzenyuy", "mtn-verify-cm", "Ransomware"):
            self.assertNotIn(needle, HTML, needle)

    def test_uses_only_the_new_api_routes(self):
        urls = set(re.findall(r'fetch\(\s*"(/[^"?]*)', SCRIPT))
        self.assertEqual(urls, {"/api/lessons", "/api/lessons/", "/api/chat", "/api/quiz/submit",
                                "/api/subscribe", "/api/certificate"})
        self.assertNotIn("/validate-code", HTML)

    def test_input_limit_matches_the_server(self):
        self.assertIn(f'maxlength="{MAX_QUESTION_CHARS}"', HTML)

    def test_certificate_name_is_written_with_textcontent(self):
        render = SCRIPT[SCRIPT.index("function renderCert"):SCRIPT.index("function renderCert") + 2500]
        self.assertIn('g("certName").textContent=d.name', render)
        self.assertNotIn("d.name+", render)
        self.assertNotIn("+d.name", render)

    def test_no_developer_instructions_visible_to_customers(self):
        for needle in ("uvicorn", "127.0.0.1", "videoId in index.html", "In index.html find"):
            self.assertNotIn(needle, HTML, needle)

    def test_page_is_small(self):
        self.assertLess(len(HTML.encode("utf-8")), 100 * 1024)


if __name__ == "__main__":
    unittest.main()
