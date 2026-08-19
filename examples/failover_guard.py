#!/usr/bin/env python3
"""Failover guard — pattern ① from the README.

When the primary "brain" (a hosted LLM) is unreachable, keep the agent from going
dark: emit a guaranteed "alive, degraded" line, then best-effort add a sentence
from a local backup model to prove the backstop is genuinely alive.

Design rules encoded here:
  - Detect the primary on the SAME path the agent actually uses (inject `primary_ok`).
  - Anti-flap: declare down only after THRESHOLD consecutive failures; announce once.
  - The guaranteed status line never depends on the (slow, possibly-failing) backup.

This is a self-contained reference; wire `notify`, `primary_ok`, and `backup_say`
to your own stack. No credentials, hosts, or paths are hardcoded.
"""
import json
import os
import time
import urllib.request

STATE = os.environ.get("FAILOVER_STATE", "/tmp/failover-state.json")
THRESHOLD = int(os.environ.get("FAILOVER_THRESHOLD", "2"))
# OpenAI-compatible local backup endpoint (e.g. a local vLLM/llama.cpp server).
BACKUP_URL = os.environ.get("BACKUP_LLM_URL", "http://localhost:8000/v1")
BACKUP_MODEL = os.environ.get("BACKUP_LLM_MODEL", "local-model")


def notify(line: str) -> None:
    """Deliver one status line to wherever a human will see it (chat, log, page).

    Replace with your transport. Crucially: this path must NOT depend on the
    primary LLM — that's the thing that's down.
    """
    print(line)


def primary_ok() -> tuple[bool, str]:
    """Return (is_up, reason). MUST probe the primary the same way you really call it.

    A separate 'health endpoint' can disagree with your actual call path and become
    its own silent failure. Here we leave it abstract — plug in your real call.
    """
    raise NotImplementedError("wire this to your real primary-LLM call path")


def backup_say(prompt: str, timeout: int = 30) -> str | None:
    """Best-effort: ask the local backup model one short thing. Never raises."""
    body = json.dumps({
        "model": BACKUP_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 160,
        "temperature": 0.7,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{BACKUP_URL}/chat/completions", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001 — a failing backup must not break the guaranteed line
        return None


def _load() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"down": False, "since": None, "fail_count": 0}


def _save(st: dict) -> None:
    with open(STATE, "w") as f:
        json.dump(st, f)


def survival_beat(reason: str) -> None:
    """Guaranteed line first, smart line second."""
    notify(f"[ALERT] primary brain unreachable ({reason}) -> failing over to local backup; still alive.")
    word = backup_say("The primary API is down. In one sentence, reassure that you're alive locally.")
    if word:
        notify(f"[ALERT] (from backup brain) {word}")


def cycle(*, force_down: bool = False) -> None:
    st = _load()
    ok, reason = (False, "forced") if force_down else primary_ok()

    if ok:
        if st.get("down"):
            notify(f"[OK] primary brain recovered (was down since {st.get('since')}).")
        _save({"down": False, "since": None, "fail_count": 0})
        return

    fc = st.get("fail_count", 0) + 1
    if not st.get("down") and fc < THRESHOLD and not force_down:
        _save({"down": False, "since": None, "fail_count": fc})  # one blip != an outage
        return
    if st.get("down"):
        return  # already announced; don't double-fire

    survival_beat(reason)
    _save({"down": True, "since": time.strftime("%Y-%m-%d %H:%M"), "fail_count": fc})


if __name__ == "__main__":
    # Demo without a real primary: force an outage, then a recovery.
    os.environ["FAILOVER_STATE"] = STATE
    cycle(force_down=True)   # declares down, fires survival beat (backup optional)
    cycle(force_down=True)   # still-down: no double-fire
