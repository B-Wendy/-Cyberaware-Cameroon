import os
import time
import unittest
from pathlib import Path
from unittest import mock

import access
import tests.helpers  # noqa: F401  (sets test secrets)


class TokenTests(unittest.TestCase):
    def test_genuine_token_is_valid(self):
        issued = access.issue_access_token("sub")
        status, payload = access.access_status(issued["token"])
        self.assertEqual(status, "valid")
        self.assertEqual(payload["tier"], "sub")

    def test_missing_token(self):
        self.assertEqual(access.access_status(None)[0], "none")
        self.assertEqual(access.access_status("")[0], "none")

    def test_garbage_is_invalid(self):
        for bad in ["abc", "v1.a.b", "x.y.z", "v1..", "v1.%%%.%%%", "A" * 5000]:
            self.assertEqual(access.access_status(bad)[0], "invalid", bad[:20])

    def test_edited_payload_is_rejected(self):
        issued = access.issue_access_token("sub")
        head, body, sig = issued["token"].split(".")
        # attacker swaps in a payload that says tier=admin with a far-future expiry
        import base64, json
        forged_body = base64.urlsafe_b64encode(json.dumps(
            {"k": "acc", "tier": "admin", "exp": int(time.time()) + 10**9}).encode()).rstrip(b"=").decode()
        self.assertEqual(access.access_status(f"{head}.{forged_body}.{sig}")[0], "invalid")

    def test_token_signed_with_another_secret_is_rejected(self):
        with mock.patch.dict(os.environ, {"TOKEN_SECRET": "some-other-secret"}):
            foreign = access.issue_access_token("sub")["token"]
        self.assertEqual(access.access_status(foreign)[0], "invalid")

    def test_expired_token(self):
        issued = access.issue_access_token("sub", now=time.time() - access.SUBSCRIPTION_SECONDS - 10)
        status, _ = access.access_status(issued["token"])
        self.assertEqual(status, "expired")
        self.assertFalse(access.is_entitled(issued["token"]))

    def test_token_just_inside_expiry_is_valid(self):
        now = 1_000_000.0
        issued = access.issue_access_token("sub", now=now)
        self.assertEqual(access.access_status(issued["token"], now=now + access.SUBSCRIPTION_SECONDS - 1)[0], "valid")
        self.assertEqual(access.access_status(issued["token"], now=now + access.SUBSCRIPTION_SECONDS)[0], "expired")

    def test_progress_token_cannot_be_used_as_access_token(self):
        prog = access.issue_progress_token({0: 5})
        self.assertEqual(access.access_status(prog)[0], "invalid")
        self.assertFalse(access.is_entitled(prog))

    def test_access_token_cannot_be_used_as_progress(self):
        self.assertEqual(access.read_progress(access.issue_access_token("sub")["token"]), {})

    def test_progress_round_trip(self):
        token = access.issue_progress_token({0: 5, 3: 4})
        self.assertEqual(access.read_progress(token), {0: 5, 3: 4})

    def test_edited_progress_is_rejected(self):
        token = access.issue_progress_token({0: 1})
        head, body, sig = token.split(".")
        import base64, json
        forged = base64.urlsafe_b64encode(json.dumps({"k": "prg", "best": {"0": 5}}).encode()).rstrip(b"=").decode()
        self.assertEqual(access.read_progress(f"{head}.{forged}.{sig}"), {})

    def test_admin_token_lasts_shorter_than_a_subscription(self):
        self.assertLess(access.ADMIN_SECONDS, access.SUBSCRIPTION_SECONDS)


class CodeTests(unittest.TestCase):
    def test_subscriber_code(self):
        self.assertEqual(access.check_code("SUB-TEST-1"), "sub")
        self.assertEqual(access.check_code("  sub-test-2 "), "sub")     # trimmed, case-insensitive

    def test_admin_code(self):
        self.assertEqual(access.check_code("ADMIN-TEST-CODE"), "admin")

    def test_wrong_codes(self):
        for bad in ["", "   ", "SUB-TEST", "SUB-TEST-3", "CYBER-001", "CYBER-2025", "x" * 100]:
            self.assertIsNone(access.check_code(bad), bad)

    def test_old_hard_coded_codes_no_longer_work(self):
        for old in ["CYBER-2025"] + [f"CYBER-{i:03d}" for i in range(1, 11)]:
            self.assertIsNone(access.check_code(old))

    def test_nothing_is_accepted_when_no_codes_are_configured(self):
        with mock.patch.dict(os.environ, {"ACCESS_CODES": "", "ADMIN_ACCESS_CODE": ""}):
            self.assertIsNone(access.check_code("SUB-TEST-1"))
            self.assertIsNone(access.check_code(""))

    def test_empty_admin_code_cannot_be_matched_by_empty_input(self):
        with mock.patch.dict(os.environ, {"ADMIN_ACCESS_CODE": ""}):
            self.assertIsNone(access.check_code(""))

    def test_codes_are_not_in_the_source_code(self):
        source = Path(access.__file__).read_text(encoding="utf-8")
        for needle in ["SUB-TEST", "ADMIN-TEST", "CYBER-0"]:
            self.assertNotIn(needle, source)


class CertificateReferenceTests(unittest.TestCase):
    def test_reference_depends_on_name_date_and_scores(self):
        best = {i: 5 for i in range(10)}
        a = access.certificate_reference("Ada Obi", "2026-10-13", best)
        self.assertTrue(a.startswith("CAC-"))
        self.assertEqual(a, access.certificate_reference("Ada Obi", "2026-10-13", best))
        self.assertNotEqual(a, access.certificate_reference("Ada Obo", "2026-10-13", best))
        self.assertNotEqual(a, access.certificate_reference("Ada Obi", "2026-10-14", best))
        self.assertNotEqual(a, access.certificate_reference("Ada Obi", "2026-10-13", {**best, 3: 4}))


if __name__ == "__main__":
    unittest.main()
