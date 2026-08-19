#!/usr/bin/env python3
"""Model identity checker — pattern ② from the README.

Detect "the model changed under you" for an OpenAI-compatible endpoint whose
*served name stays the same* while the actual model behind it changes. Bind your
calibrated constants to the model's fingerprint, so a swap forces re-checking
instead of silently rotting.

Fingerprint = things that actually change across models:
  - served model id (from /v1/models)
  - max context length (from /v1/models; a shrinking window is a classic silent breaker)
  - a behavioral probe hash (hash of the model's reply to a fixed prompt) as a
    stand-in for the chat-template / decoding identity.

Usage:
  python3 model_identity.py            # compare live endpoint to recorded baseline
  python3 model_identity.py --record   # record current model as the baseline (do this
                                        # ONLY after you've re-checked the calibrations)
"""
import hashlib
import json
import os
import sys
import urllib.request

BASE = os.environ.get("LLM_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("LLM_MODEL", "local-model")
RECORD = os.environ.get("IDENTITY_RECORD", "model-identity.json")

# Constants you tuned for a specific model. When the fingerprint changes, every one
# of these is suspect until re-measured. Keep the list next to the checker.
CALIBRATIONS = [
    "prompt/context budget (sized to the model's real window)",
    "max_tokens estimates for thinking on/off",
    "any classifier thresholds tuned on this model's output distribution",
]


def _get(path: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)


def _post(path: str, obj: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        BASE + path, json.dumps(obj).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fingerprint() -> dict:
    models = _get("/models")["data"][0]
    probe = _post("/chat/completions", {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly: PROBE-OK"}],
        "max_tokens": 16,
        "temperature": 0,
    })["choices"][0]["message"]["content"]
    return {
        "served_id": models.get("id"),
        "max_model_len": models.get("max_model_len"),
        "probe_hash": hashlib.sha256(probe.encode()).hexdigest()[:16],
    }


def main() -> int:
    fp = fingerprint()
    if "--record" in sys.argv:
        with open(RECORD, "w") as f:
            json.dump(fp, f, indent=2)
        print("recorded baseline:", fp)
        return 0

    try:
        with open(RECORD) as f:
            base = json.load(f)
    except (OSError, ValueError):
        print("no baseline yet — run with --record after checking calibrations.")
        print("current:", fp)
        return 4

    diffs = {k: (base.get(k), fp.get(k)) for k in fp if base.get(k) != fp.get(k)}
    if not diffs:
        print("OK — model identity matches baseline; calibrations can be trusted.")
        return 0

    print("CHANGED — the model behind the endpoint is not the one you calibrated for:")
    for k, (was, now) in diffs.items():
        print(f"  {k}: {was} -> {now}")
    print("\nRe-check these calibrations, then --record:")
    for c in CALIBRATIONS:
        print(f"  - {c}")
    # Note the blind spot honestly: during a reload the endpoint may be briefly
    # unreachable and this check can't run — it's a *delayed* alarm, not a silent one.
    return 3


if __name__ == "__main__":
    sys.exit(main())
