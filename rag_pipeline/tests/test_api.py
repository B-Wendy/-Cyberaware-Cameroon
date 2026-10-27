import json
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import access
import app as app_module
import rag
from ratelimit import RateLimiter
from tests.helpers import FakeCollection, FakeTimeout, StubLLM, build_embedder_and_records

SUB = {"X-Access-Token": None}


def sub_headers(progress=None, tier_code="SUB-TEST-1"):
    client = TestClient(app_module.app)
    token = client.post("/api/subscribe", json={"code": tier_code}).json()["token"]
    headers = {"X-Access-Token": token}
    if progress:
        headers["X-Progress-Token"] = progress
    return headers


class ApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder, cls.records = build_embedder_and_records()

    def setUp(self):
        app_module.chat_limiter = RateLimiter(20)
        app_module.code_limiter = RateLimiter(5)
        self.collection = FakeCollection(self.embedder, self.records)
        self.llm = StubLLM()
        for p in (mock.patch.object(rag, "get_embedder", lambda: self.embedder),
                  mock.patch.object(rag, "get_collection", lambda: self.collection),
                  mock.patch.object(app_module, "get_collection", lambda: self.collection),
                  mock.patch.object(rag, "make_llm_client", lambda: self.llm)):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app_module.app)

    def correct_answers(self, lesson_id):
        return [q["cor"] for q in app_module.store.body(lesson_id)["quiz"]]

    def submit(self, lesson_id, answers, headers=None):
        return self.client.post("/api/quiz/submit", json={"lesson_id": lesson_id, "answers": answers},
                                headers=headers or {})


class RouteTests(ApiBase):
    def test_exactly_the_endpoints_of_table_4_9(self):
        found = set()
        for r in app_module.app.routes:
            if r.path.startswith("/api") or r.path == "/":
                for m in r.methods:
                    if m != "HEAD":
                        found.add((m, r.path))
        self.assertEqual(found, {
            ("GET", "/"), ("POST", "/api/chat"), ("GET", "/api/lessons"), ("GET", "/api/lessons/{lesson_id}"),
            ("POST", "/api/quiz/submit"), ("POST", "/api/subscribe"), ("GET", "/api/certificate"),
            ("GET", "/api/health")})

    def test_old_insecure_endpoints_are_gone(self):
        self.assertEqual(self.client.post("/validate-code", json={"code": "CYBER-001"}).status_code, 404)
        self.assertEqual(self.client.post("/chat", json={"message": "hi"}).status_code, 404)

    def test_front_end_is_served_with_security_headers(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("default-src 'self'", r.headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", r.headers["content-security-policy"])
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["x-frame-options"], "DENY")

    def test_api_responses_are_not_cacheable(self):
        self.assertEqual(self.client.get("/api/lessons").headers["cache-control"], "no-store")

    def test_initial_payload_is_under_200_kilobytes(self):
        page = len(self.client.get("/").content)
        catalogue = len(self.client.get("/api/lessons").content)
        self.assertLess(page + catalogue, 200 * 1024, f"{page + catalogue} bytes")

    def test_health_ok_and_degraded(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body["status"], body["collection"], body["chunks"]), ("ok", "cyberaware", 44))

        def boom():
            raise RuntimeError("no collection")
        with mock.patch.object(app_module, "get_collection", boom):
            r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["status"], "degraded")


class LessonAccessTests(ApiBase):
    def test_anonymous_catalogue_marks_eight_locked_and_hides_content(self):
        r = self.client.get("/api/lessons")
        data = r.json()
        self.assertEqual(len(data["lessons"]), 10)
        self.assertEqual([l["locked"] for l in data["lessons"]], [False, False] + [True] * 8)
        self.assertFalse(data["entitled"])
        text = json.dumps(data["lessons"])
        for forbidden in ('"quiz"', '"cor"', '"sc"', '"exp"'):
            self.assertNotIn(forbidden, text)

    def test_free_lessons_are_open_to_everyone(self):
        for i in (0, 1):
            r = self.client.get(f"/api/lessons/{i}")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.json()["quiz"]), 5)

    def test_locked_lesson_returns_402_and_no_lesson_content(self):
        for i in range(2, 10):
            r = self.client.get(f"/api/lessons/{i}")
            self.assertEqual(r.status_code, 402, i)
            self.assertEqual(r.json()["detail"], "payment_required")
            self.assertEqual(r.json()["price_fcfa"], 2500)
            for secret in ("quiz", "sc", "msg", "cor", "opts"):
                self.assertNotIn(secret, r.json())

    def test_subscriber_token_unlocks_everything(self):
        h = sub_headers()
        for i in range(10):
            self.assertEqual(self.client.get(f"/api/lessons/{i}", headers=h).status_code, 200, i)
        cat = self.client.get("/api/lessons", headers=h).json()
        self.assertTrue(cat["entitled"])
        self.assertFalse(any(l["locked"] for l in cat["lessons"]))

    def test_admin_code_unlocks(self):
        h = sub_headers(tier_code="ADMIN-TEST-CODE")
        self.assertEqual(self.client.get("/api/lessons/9", headers=h).status_code, 200)
        self.assertEqual(self.client.get("/api/lessons", headers=h).json()["tier"], "admin")

    def test_browser_storage_trick_does_not_work(self):
        # The old bug: setting a flag in the browser unlocked everything. Try the usual suspects.
        for headers in ({"X-Access-Token": "1"}, {"X-Access-Token": "premium"}, {"X-Access-Token": "true"},
                        {"cap": "1"}, {"X-Premium": "1"}, {"Cookie": "cap=1"}):
            self.assertEqual(self.client.get("/api/lessons/5", headers=headers).status_code, 402, headers)

    def test_forged_and_wrong_kind_tokens_are_refused(self):
        genuine = access.issue_access_token("sub")["token"]
        head, body, sig = genuine.split(".")
        flipped = f"{head}.{body}.{sig[:-2]}AA"
        for token in (flipped, access.issue_progress_token({0: 5}), "v1.e30.AAAA"):
            self.assertEqual(self.client.get("/api/lessons/5", headers={"X-Access-Token": token}).status_code,
                             402)

    def test_expired_subscription_is_refused_and_reported(self):
        old = access.issue_access_token("sub", now=time.time() - access.SUBSCRIPTION_SECONDS - 60)["token"]
        h = {"X-Access-Token": old}
        self.assertEqual(self.client.get("/api/lessons/5", headers=h).status_code, 402)
        data = self.client.get("/api/lessons", headers=h).json()
        self.assertEqual(data["token_status"], "expired")
        self.assertFalse(data["entitled"])

    def test_unknown_lesson(self):
        self.assertEqual(self.client.get("/api/lessons/10").status_code, 404)
        self.assertEqual(self.client.get("/api/lessons/-1").status_code, 404)
        self.assertEqual(self.client.get("/api/lessons/abc").status_code, 422)


class SubscribeTests(ApiBase):
    def test_good_code_returns_a_working_token(self):
        r = self.client.post("/api/subscribe", json={"code": " sub-test-1 "})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["tier"], "sub")
        self.assertGreater(data["expires_at"], time.time() + 29 * 86400)
        self.assertTrue(access.is_entitled(data["token"]))

    def test_bad_codes_get_403_and_no_token(self):
        for code in ("WRONG", "CYBER-001", "CYBER-2025", "sub-test-"):
            r = self.client.post("/api/subscribe", json={"code": code})
            self.assertEqual(r.status_code, 403, code)
            self.assertEqual(r.json(), {"valid": False})

    def test_empty_or_oversized_code_is_a_validation_error(self):
        self.assertEqual(self.client.post("/api/subscribe", json={"code": ""}).status_code, 422)
        self.assertEqual(self.client.post("/api/subscribe", json={"code": "x" * 65}).status_code, 422)
        self.assertEqual(self.client.post("/api/subscribe", json={}).status_code, 422)

    def test_guessing_is_rate_limited(self):
        statuses = [self.client.post("/api/subscribe", json={"code": f"GUESS-{i}"}).status_code for i in range(8)]
        self.assertEqual(statuses[:5], [403] * 5)
        self.assertEqual(statuses[5:], [429] * 3)
        # once blocked, even the right code is refused until the minute is over
        self.assertEqual(self.client.post("/api/subscribe", json={"code": "SUB-TEST-1"}).status_code, 429)

    def test_codes_are_never_echoed_back(self):
        r = self.client.post("/api/subscribe", json={"code": "SECRET-GUESS"})
        self.assertNotIn("SECRET-GUESS", r.text)


class QuizTests(ApiBase):
    def test_free_lesson_quiz_marked_on_the_server(self):
        r = self.submit(0, self.correct_answers(0))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual((d["score"], d["total"], d["percent"], d["passed"]), (5, 5, 100, True))
        self.assertEqual(d["passed_lessons"], [0])
        self.assertEqual(access.read_progress(d["progress_token"]), {0: 5})

    def test_paid_lesson_quiz_needs_a_subscription(self):
        r = self.submit(4, self.correct_answers(4))
        self.assertEqual(r.status_code, 402)
        self.assertEqual(self.submit(4, self.correct_answers(4), sub_headers()).status_code, 200)

    def test_the_server_ignores_what_the_browser_claims(self):
        wrong = [(c + 1) % 4 for c in self.correct_answers(0)]
        d = self.submit(0, wrong).json()
        self.assertEqual((d["score"], d["passed"]), (0, False))
        self.assertEqual(d["passed_lessons"], [])

    def test_best_score_is_kept(self):
        first = self.submit(0, self.correct_answers(0)).json()["progress_token"]
        worse = [(c + 1) % 4 for c in self.correct_answers(0)]
        d = self.submit(0, worse, {"X-Progress-Token": first}).json()
        self.assertEqual(d["score"], 0)
        self.assertEqual(d["best_score"], 5)
        self.assertEqual(access.read_progress(d["progress_token"]), {0: 5})

    def test_progress_accumulates_across_lessons(self):
        h = sub_headers()
        token = None
        for i in (0, 1, 2):
            headers = dict(h)
            if token:
                headers["X-Progress-Token"] = token
            token = self.submit(i, self.correct_answers(i), headers).json()["progress_token"]
        self.assertEqual(access.read_progress(token), {0: 5, 1: 5, 2: 5})

    def test_forged_progress_token_is_ignored(self):
        d = self.submit(0, [(c + 1) % 4 for c in self.correct_answers(0)],
                        {"X-Progress-Token": "v1.e30.AAAA"}).json()
        self.assertEqual(d["passed_lessons"], [])

    def test_bad_submissions(self):
        self.assertEqual(self.submit(0, [0, 0, 0]).status_code, 422)
        self.assertEqual(self.submit(0, [0, 0, 0, 0, 9]).status_code, 422)
        self.assertEqual(self.submit(0, [0, 0, 0, 0, -1]).status_code, 422)
        self.assertEqual(self.submit(99, [0, 0, 0, 0, 0]).status_code, 404)
        self.assertEqual(self.client.post("/api/quiz/submit", json={"lesson_id": 0}).status_code, 422)
        self.assertEqual(self.client.post("/api/quiz/submit", json={"lesson_id": 0, "answers": ["a"]}).status_code, 422)


class CertificateTests(ApiBase):
    def complete_everything(self, headers, skip=None, perfect=True):
        token = None
        for i in range(10):
            if i == skip:
                continue
            answers = self.correct_answers(i)
            if not perfect:
                answers[0] = (answers[0] + 1) % 4          # 4/5 = 80%: still a pass
            h = dict(headers)
            if token:
                h["X-Progress-Token"] = token
            token = self.submit(i, answers, h).json()["progress_token"]
        return token

    def cert(self, name, headers):
        return self.client.get("/api/certificate", params={"name": name}, headers=headers)

    def test_needs_a_subscription(self):
        self.assertEqual(self.cert("Ada Obi", {}).status_code, 402)

    def test_incomplete_progress_is_refused_with_the_missing_lessons(self):
        h = sub_headers()
        progress = self.complete_everything(h, skip=6)
        r = self.cert("Ada Obi", {**h, "X-Progress-Token": progress})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["missing"], [6])

    def test_no_progress_at_all(self):
        r = self.cert("Ada Obi", sub_headers())
        self.assertEqual(r.status_code, 409)
        self.assertEqual(len(r.json()["missing"]), 10)

    def test_certificate_issued_when_all_ten_are_passed(self):
        h = sub_headers()
        progress = self.complete_everything(h)
        r = self.cert("Mary-Ann O'Neil", {**h, "X-Progress-Token": progress})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["name"], "Mary-Ann O'Neil")
        self.assertTrue(d["reference"].startswith("CAC-"))
        self.assertEqual(len(d["lessons"]), 10)
        self.assertEqual(d["pass_percent"], 80)
        self.assertRegex(d["completed_on"], r"^\d{4}-\d{2}-\d{2}$")

    def test_exactly_80_percent_in_every_lesson_is_enough(self):
        h = sub_headers()
        progress = self.complete_everything(h, perfect=False)
        self.assertEqual(self.cert("Ada Obi", {**h, "X-Progress-Token": progress}).status_code, 200)

    def test_60_percent_in_a_lesson_is_not_enough(self):
        h = sub_headers()
        token = None
        for i in range(10):
            answers = self.correct_answers(i)
            if i == 3:
                answers[0] = (answers[0] + 1) % 4
                answers[1] = (answers[1] + 1) % 4          # 3/5 = 60%
            hh = dict(h)
            if token:
                hh["X-Progress-Token"] = token
            token = self.submit(i, answers, hh).json()["progress_token"]
        r = self.cert("Ada Obi", {**h, "X-Progress-Token": token})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["missing"], [3])

    def test_expired_subscription_cannot_get_a_certificate(self):
        h = sub_headers()
        progress = self.complete_everything(h)
        expired = access.issue_access_token("sub", now=time.time() - access.SUBSCRIPTION_SECONDS - 60)["token"]
        r = self.cert("Ada Obi", {"X-Access-Token": expired, "X-Progress-Token": progress})
        self.assertEqual(r.status_code, 402)

    def test_hand_made_progress_cannot_get_a_certificate(self):
        h = sub_headers()
        fake = {"X-Progress-Token": "v1.eyJiZXN0Ijp7fX0.AAAA"}
        self.assertEqual(self.cert("Ada Obi", {**h, **fake}).status_code, 409)

    def test_names_that_could_carry_code_are_rejected(self):
        h = sub_headers()
        progress = self.complete_everything(h)
        full = {**h, "X-Progress-Token": progress}
        for bad in ["<script>alert(1)</script>", "Ada<b>", "Ada & Co", "A", "", "x" * 61, "12345", "Ada\"Obi",
                    "Ada; DROP TABLE", "{{7*7}}"]:
            self.assertEqual(self.cert(bad, full).status_code, 422, bad)
        for good in ["Éloïse Nkémelé", "Jean-Pierre", "Mbiydzenyuy Wendy Bongsisi", "D. Okafor"]:
            self.assertEqual(self.cert(good, full).status_code, 200, good)

    def test_reference_is_stable_for_the_same_certificate(self):
        h = sub_headers()
        progress = self.complete_everything(h)
        full = {**h, "X-Progress-Token": progress}
        a = self.cert("Ada Obi", full).json()["reference"]
        b = self.cert("Ada Obi", full).json()["reference"]
        c = self.cert("Ada Obo", full).json()["reference"]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class ClientAddressTests(ApiBase):
    """Rate limits must not be dodged by forging X-Forwarded-For."""

    def hammer(self, headers_for):
        return [self.client.post("/api/chat", json={"message": "zzzqx", "language": "en"},
                                 headers=headers_for(i)).status_code for i in range(23)]

    def test_forged_header_is_ignored_when_no_proxy_is_configured(self):
        codes = self.hammer(lambda i: {"X-Forwarded-For": f"10.0.0.{i}"})
        self.assertEqual(codes.count(429), 3)

    def test_forged_left_entries_do_not_help_behind_a_proxy(self):
        with mock.patch.object(app_module, "PROXY_HOPS", 1):
            codes = self.hammer(lambda i: {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"})
        self.assertEqual(codes.count(429), 3)          # the real address (right-most) never changed

    def test_different_real_visitors_behind_a_proxy_get_separate_limits(self):
        with mock.patch.object(app_module, "PROXY_HOPS", 1):
            codes = self.hammer(lambda i: {"X-Forwarded-For": f"203.0.113.{i}"})
        self.assertEqual(codes.count(429), 0)

    def test_hsts_only_when_the_proxy_says_https(self):
        with mock.patch.object(app_module, "PROXY_HOPS", 1):
            self.assertIn("strict-transport-security", self.client.get("/api/lessons", headers={"X-Forwarded-Proto": "https"}).headers)
            self.assertNotIn("strict-transport-security", self.client.get("/api/lessons").headers)


class ChatApiTests(ApiBase):
    def ask(self, message, language="auto"):
        return self.client.post("/api/chat", json={"message": message, "language": language})

    def test_grounded_answer(self):
        r = self.ask("What makes a strong password?", "en")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual((d["mode"], d["language"]), ("grounded", "en"))
        self.assertTrue(d["sources"])

    def test_language_is_detected_when_not_chosen(self):
        d = self.ask("Qu'est-ce qu'un mot de passe robuste ?").json()
        self.assertEqual(d["language"], "fr")

    def test_input_length_is_capped_at_500_characters(self):
        ok = "password " * 55                                    # 495 characters after trimming
        self.assertLessEqual(len(ok.strip()), 500)
        self.assertEqual(self.ask(ok).status_code, 200)
        self.assertEqual(self.ask("a" * 501).status_code, 422)
        self.assertEqual(self.ask("a" * 5000).status_code, 422)
        self.assertEqual(self.llm.calls[-1]["messages"][1]["content"], ok.strip())

    def test_empty_questions_are_rejected(self):
        for blank in ("", "   ", "\n\t"):
            self.assertEqual(self.ask(blank).status_code, 422)

    def test_rate_limit_is_20_per_minute_per_visitor(self):
        statuses = [self.ask("What makes a strong password?", "en").status_code for _ in range(23)]
        self.assertEqual(statuses[:20], [200] * 20)
        self.assertEqual(statuses[20:], [429] * 3)
        r = self.ask("What makes a strong password?", "fr")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Trop de requêtes", r.json()["answer"])

    def test_html_in_a_question_is_treated_as_plain_text(self):
        payload = "<script>alert(1)</script> password"
        r = self.ask(payload, "en")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.llm.calls[-1]["messages"][1]["content"], payload)   # passed as data, never executed
        self.assertIn("application/json", r.headers["content-type"])

    def test_model_failure_still_returns_an_answer(self):
        self.llm.error = FakeTimeout("slow")
        d = self.ask("What makes a strong password?", "en").json()
        self.assertEqual(d["mode"], "degraded")
        self.assertIn("password", d["answer"].lower())

    def test_missing_knowledge_base_gives_503_without_a_stack_trace(self):
        def boom():
            raise RuntimeError("Embedder not found. Run `python ingest.py` first. /secret/path")
        with mock.patch.object(rag, "get_embedder", boom):
            r = self.ask("What makes a strong password?", "en")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("secret/path", r.text)
        self.assertNotIn("Traceback", r.text)
        self.assertEqual(r.json()["mode"], "unavailable")


if __name__ == "__main__":
    unittest.main()
