"""auto-pin rule: every new interactive session is pinned automatically.

Pure logic with no Hermes imports, so it can be tested offline.

Pinned:   top-level sessions from an interactive surface (``desktop``, ``cli``, ``tui``), plus
          branches the user forks off one of them.
Skipped:  one-shot / cron / api_server / messaging runs, subagent and delegate children,
          compression continuations (they inherit the lineage pin anyway), hidden or archived
          rows, and any row that started more than an hour ago (``on_session_start`` also fires
          when an OLD session's stored prompt is rebuilt; that must not re-pin something the
          user unpinned).

Every automatic pin is appended to a ledger (``<hermes home>/auto-pin/ledger.txt``) so a session
is decided once: unpinning it in the sidebar sticks, and other tooling can tell an automatic pin
from one made by hand.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

INTERACTIVE_SOURCES = frozenset({"desktop", "cli", "tui"})
MAX_AGE_S = 3600


def ledger_path(home: str | os.PathLike) -> Path:
    return Path(home) / "auto-pin" / "ledger.txt"


def in_ledger(home, session_id: str) -> bool:
    p = ledger_path(home)
    if not session_id or not p.exists():
        return False
    try:
        with p.open(encoding="utf-8") as fh:
            return any(line.split("\t", 1)[0] == session_id for line in fh)
    except OSError:
        return False


def record(home, session_id: str) -> None:
    p = ledger_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:  # O_APPEND: one short line is atomic across processes
        fh.write(f"{session_id}\t{int(time.time())}\n")


def _model_config(row: dict) -> dict:
    mc = row.get("model_config")
    if isinstance(mc, dict):
        return mc
    if isinstance(mc, str) and mc:
        try:
            v = json.loads(mc)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


def decide(row: dict, now: float | None = None) -> tuple[bool, str]:
    """(pin?, reason) for a sessions row dict as returned by ``SessionDB.get_session``."""
    if not row:
        return False, "no row"
    if row.get("pinned"):
        return False, "already pinned"
    if row.get("hidden"):
        return False, "hidden"
    if row.get("archived"):
        return False, "archived"
    src = (row.get("source") or "").lower()
    if src not in INTERACTIVE_SOURCES:
        return False, f"source {src or '?'}"
    if row.get("parent_session_id"):
        mc = _model_config(row)
        if mc.get("_branched_from") != row.get("parent_session_id"):
            return False, "child session"
    started = row.get("started_at") or 0
    if started and (now or time.time()) - float(started) > MAX_AGE_S:
        return False, "not new"
    return True, "new interactive session"
