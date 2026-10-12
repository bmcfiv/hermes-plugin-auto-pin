import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("auto_pin_core", Path(__file__).resolve().parent.parent / "core.py")
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


def row(**kw):
    base = {"id": "s1", "source": "desktop", "started_at": time.time(), "pinned": 0, "hidden": 0, "archived": 0}
    base.update(kw)
    return base


class DecideTests(unittest.TestCase):
    def test_new_interactive_sessions_are_pinned(self):
        for src in ("desktop", "cli", "tui", "CLI"):
            self.assertTrue(core.decide(row(source=src))[0], src)

    def test_non_interactive_sources_are_skipped(self):
        for src in ("cron", "api_server", "telegram", "", None):
            self.assertFalse(core.decide(row(source=src))[0], src)

    def test_already_pinned_hidden_archived_or_empty_are_skipped(self):
        self.assertFalse(core.decide(row(pinned=1))[0])
        self.assertFalse(core.decide(row(hidden=1))[0])
        self.assertFalse(core.decide(row(archived=1))[0])
        self.assertEqual(core.decide({}), (False, "no row"))

    def test_old_sessions_are_not_repinned(self):
        self.assertFalse(core.decide(row(started_at=time.time() - core.MAX_AGE_S - 5))[0])

    def test_child_sessions_skipped_but_user_branches_pinned(self):
        self.assertFalse(core.decide(row(parent_session_id="p"))[0])
        self.assertTrue(core.decide(row(parent_session_id="p", model_config=json.dumps({"_branched_from": "p"})))[0])
        self.assertTrue(core.decide(row(parent_session_id="p", model_config={"_branched_from": "p"}))[0])
        self.assertFalse(core.decide(row(parent_session_id="p", model_config="not json"))[0])


class LedgerTests(unittest.TestCase):
    def test_ledger_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(core.in_ledger(tmp, "s1"))
            core.record(tmp, "s1")
            self.assertTrue(core.in_ledger(tmp, "s1"))
            self.assertFalse(core.in_ledger(tmp, "s2"))
            self.assertFalse(core.in_ledger(tmp, ""))


if __name__ == "__main__":
    unittest.main()
