# Staying Honest While Nobody's Watching

Patterns for keeping a long-running, unattended AI agent **alive** and **honest** — learned by running one 24/7 on a small always-on box and watching it break in quiet, undramatic ways.

> The hard part of unattended autonomy isn't intelligence. It's that a broken agent **looks fine**. It keeps printing green. This repo is three small patterns that attack that directly:
> **① don't go dark · ② notice when the ground shifts under you · ③ distrust your own "all-clear".**

These come from real incidents operating an autonomous agent whose "brain" is an LLM, with a small **local** model as a backstop. Names, hosts, and paths are stripped; the patterns and the failure modes are the point. Reference implementations are in [`examples/`](examples/).

---

## ① The backup brain: a single-point-of-failure for cognition

**The incident.** The agent's reasoning ran through one hosted LLM. Its auth token silently expired. For **~17 hours** the agent — and the chat bot that shared the same credential — went completely silent. Nothing crashed loudly. There was just… nothing.

The root cause wasn't the token. It was that **cognition had a single point of failure** and the failure produced *silence*, which is the one signal a monitoring-by-absence setup can't see.

**The pattern.** Keep a second, independent brain — a small **local** model — and a *failover beat* that lights up when the primary is unreachable, so the agent can at least say "I'm alive, degraded" instead of vanishing.

Three design rules that matter more than the code:

1. **Detect on the same path you actually use.** Don't invent a separate health-probe endpoint — it can disagree with the real call path and become its *own* silent failure. The failover checks the primary the exact same way the agent normally calls it.
2. **Anti-flap.** One blip is not an outage. Declare "down" only after N consecutive failures; announce the outage once and the recovery once. Flapping alerts train you to ignore them.
3. **The guaranteed line comes first, the smart line second.** The "I'm alive" signal must not depend on the slow/possibly-failing backup model. Emit a fixed status line first; *then*, best-effort, let the local model add a sentence. If the local brain can answer, that's proof it's genuinely alive — a bonus, not a dependency.

See [`examples/failover_guard.py`](examples/failover_guard.py).

---

## ② Silent swaps: the model changes under you

**The incident.** The local backstop model was upgraded to a newer version. Same endpoint name, same API — but the new model's **context window was 1/8 the size** of the old one. The agent's "load my identity + memories into the prompt" routine had a fixed budget sized for the *old*, larger window. On the new model every call overflowed the context limit by a hair and returned a hard error.

Result: the **backup brain was 100% dead** — and nobody noticed, because nothing exercised it. The insurance had quietly rotted. If the primary had failed during that window, the failover from ① would have lit up… and found no one home.

**The pattern.** Treat "the model changed" as a first-class event.

- **Fingerprint the model**, not its display name. Names lie — the same served name can front a totally different model. Fingerprint on things that actually change: the chat-template hash, the max context length, the real underlying model id.
- **Bind calibration to the fingerprint.** Any tuned constant (prompt budgets, token estimates, thresholds) is *owned* by a specific model fingerprint. When the fingerprint changes, a checker lists every calibrated value that now needs re-checking. A copy-pasted default is not a declared dependency; a fingerprint-bound one is.
- **Size to the live limit, not a constant.** The overflow fix wasn't "pick a smaller number." It was: **read the model's real context window at runtime** and derive the budget from it, with a hard cap and a measured chars-per-token rate. That way the *next* swap can't silently re-break it.
- **Know your blind spot.** During the swap itself (the minutes the endpoint is reloading) the fingerprint is briefly unreachable and the check degrades to "green." So it's not a *silent* check — it's a *delayed* one. Design it to alarm the instant the new model is live, and say so out loud.

See [`examples/model_identity.py`](examples/model_identity.py).

---

## ③ The green lie: when the monitor and the thing it protects disagree

The theme under both incidents: **a monitor can report "green" while the thing it's supposed to protect is broken.** The backup brain above was "green" (endpoint up, name unchanged) while it was actually dead.

This isn't a library — it's a discipline. A few forms it takes, all observed in practice:

- **The pass/fail line measures the wrong quantity.** A classifier "passes" at 83% detail-match while the decision it actually drives (a coarse binary) is fine — or the reverse: a grader posts high "balanced accuracy" while its true-negative rate is 17%, i.e. it waves through 83% of wrong answers.
- **Insurance that nothing exercises rots to green.** If no code path ever calls the failover brain, "the endpoint is up" is not evidence it works. Exercise your fallbacks, or they're decorative.
- **Silence reads as success.** Absence of an alert is not the same as "fine." Build for *positive* liveness signals, not the lack of a complaint.

The working antidote is boring: **before you write down a conclusion, measure one thing** — the spread, the denominator, the identity of the thing you're looking at, how much of the variance your explanation actually covers. Distrust the word "green" until you can say precisely *what* is being called green.

---

## Why negative-results discipline is the real deliverable

None of this made the agent smarter. It made the agent's *self-report trustworthy* — which, for anything running unattended, is the load-bearing property. Capability and honesty are independent axes; you cannot say "it got better" in one word when one went up and the other went down.

The through-line is a pre-registration habit: **write the prediction and the pass/fail line before you run, record the measurement in a separate slot after.** It even caught its own author filling in a result *before* running once — noted, deleted, redone. That failure being visible in the record is the point, not an embarrassment.

## Who this is for

Anyone running an autonomous agent or a resident LLM unattended — a personal assistant, a cron-driven pipeline, a home-lab model server — who has felt the specific dread of "how long has this been quietly broken?"

## License

MIT — see [LICENSE](LICENSE).
