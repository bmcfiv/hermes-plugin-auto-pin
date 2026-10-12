"""auto-pin plugin: pin every new interactive session (see core.py for the rule).

Hooks ``on_session_start`` (fired on the first turn of a new session, in whichever process runs
the agent: desktop backend, gateway, CLI). Reads the row from the shared SessionDB and pins it
through ``SessionDB.set_session_pinned`` -- the same setter the sidebar's pin button uses. Any
failure is logged and swallowed: the session simply stays unpinned.
"""

from __future__ import annotations

import logging

from . import core

logger = logging.getLogger(__name__)


def _home():
    from hermes_constants import get_hermes_home

    return get_hermes_home()


def _on_session_start(session_id=None, **_kwargs) -> None:
    if not session_id:
        return
    try:
        home = _home()
        if core.in_ledger(home, session_id):
            return
        from hermes_state_registry import acquire, release

        db = acquire()
        try:
            row = db.get_session(session_id) or {}
            pin, why = core.decide(row)
            if not pin:
                logger.debug("auto-pin: %s not pinned (%s)", session_id, why)
                return
            if db.set_session_pinned(session_id, True):
                core.record(home, session_id)
                logger.info("auto-pin: pinned %s (%s)", session_id, row.get("source"))
        finally:
            release(db)
    except Exception:
        logger.warning("auto-pin: could not pin %s", session_id, exc_info=True)


def register(ctx) -> None:
    ctx.register_hook("on_session_start", _on_session_start)
