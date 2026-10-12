import importlib.util
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "auto_pin_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auto_pin_plugin"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeDB:
    def __init__(self, row):
        self.row = row
        self.pinned = []

    def get_session(self, session_id):
        return self.row

    def set_session_pinned(self, session_id, pinned):
        self.pinned.append((session_id, pinned))
        return True


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = FakeDB({"source": "desktop", "started_at": time.time()})
        self.released = []
        registry = types.ModuleType("hermes_state_registry")
        registry.acquire = lambda: self.db
        registry.release = self.released.append
        constants = types.ModuleType("hermes_constants")
        constants.get_hermes_home = lambda: Path(self.tmp.name)
        self.saved = {k: sys.modules.get(k) for k in ("hermes_state_registry", "hermes_constants")}
        sys.modules["hermes_state_registry"] = registry
        sys.modules["hermes_constants"] = constants
        self.addCleanup(self._restore)
        self.plugin = load_plugin()

    def _restore(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        sys.modules.pop("auto_pin_plugin", None)

    def test_registers_session_start_hook(self):
        calls = []
        ctx = types.SimpleNamespace(register_hook=lambda name, fn: calls.append(name))
        self.plugin.register(ctx)
        self.assertEqual(calls, ["on_session_start"])

    def test_pins_once_and_records(self):
        self.plugin._on_session_start(session_id="s1")
        self.assertEqual(self.db.pinned, [("s1", True)])
        self.assertEqual(self.released, [self.db])
        # A second start for the same session (e.g. after the user unpinned) is a no-op.
        self.plugin._on_session_start(session_id="s1")
        self.assertEqual(self.db.pinned, [("s1", True)])

    def test_skips_non_interactive_source(self):
        self.db.row = {"source": "cron", "started_at": time.time()}
        self.plugin._on_session_start(session_id="s2")
        self.assertEqual(self.db.pinned, [])

    def test_failure_is_swallowed(self):
        def boom():
            raise RuntimeError("db down")

        sys.modules["hermes_state_registry"].acquire = boom
        self.plugin._on_session_start(session_id="s3")  # must not raise
        self.assertEqual(self.db.pinned, [])


if __name__ == "__main__":
    unittest.main()
