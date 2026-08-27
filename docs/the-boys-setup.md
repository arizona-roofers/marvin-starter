# Setting Up "The Boys" — Free Multi-AI Workers

MARVIN's multi-agent protocol (`.claude/agents/the-boys.md`) uses **free CLI-based AI workers** so your paid Claude usage window is spent only on orchestration and final decisions. This guide gets the two worker CLIs installed and authenticated.

**The economics:** Claude (your main session) is the PM — smart, but every token costs plan usage. Gemini and Codex workers run on separate free/flat-rate accounts, so research and drafting fan out at zero marginal cost.

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Claude Code (Pro/Max plan) | Runs MARVIN itself |
| Git Bash (Windows) or any bash | `tools/agy-call.sh` is a bash script |
| Python 3.10+ | `tools/agy-extract.py` (reads agy's reply DB) |
| A ChatGPT account (Plus or better) | Free Codex CLI usage |
| A Google account | Antigravity (Gemini-class) OAuth |

---

## 1. Codex CLI (OpenAI worker)

```bash
npm install -g @openai/codex
codex login          # sign in with your ChatGPT account (browser OAuth)
```

Verify:

```bash
echo "" | codex exec "Say hello in five words."
```

**Gotchas:**
- **Always pipe empty stdin** (`echo "" |`) — without it, `codex exec` hangs on "Reading additional input from stdin".
- The default model comes from `~/.codex/config.toml`. Which model tiers work depends on your ChatGPT plan — the **startup banner** (`model: …`) is the only source of truth for which tier actually ran; models self-report their family name regardless of tier. If a tier returns a 400 `invalid_request_error`, switch the config default to one that works on your account.
- **Windows:** paths with spaces or parentheses break Codex's sandbox ("windows sandbox: spawn setup refresh"). Keep your MARVIN repo at a clean path (e.g. `C:\Users\you\marvin`).

## 2. Antigravity CLI (Gemini-class worker)

Google's **Antigravity** (`agy`) provides Gemini-class models over OAuth. (The old standalone `gemini` CLI's free OAuth tier was discontinued in mid-2026 — Antigravity is the replacement path.)

1. Install Antigravity (follow Google's current install instructions for the `agy` CLI).
2. Authenticate with your Google account (browser OAuth on first run).
3. Verify auth: `agy models` should list available models.

Then verify the wrapper:

```bash
bash tools/agy-call.sh "Say hello in five words."
```

**Why the wrapper exists:** `agy -p` (print mode) is broken — it authenticates and runs the model but never prints the reply to stdout. `tools/agy-call.sh` runs agy headlessly, captures the conversation id, and extracts the reply from agy's SQLite conversation DB via `tools/agy-extract.py`. **Always call `agy-call.sh`, never raw `agy -p`.**

**Fragility note:** the extractor reverse-engineers agy's on-disk format (protobuf-in-SQLite; `step_type=15` = model response). If agy ships a format change and `agy-call.sh` starts returning empty (`extract_empty` in `tools/boys-failures.log`), `tools/agy-extract.py` needs updating.

**Env knobs:**
- `AGY_MODEL` — pick a specific model (default: agy's active model)
- `AGY_HARD_TIMEOUT` — outer kill timeout in seconds (default 180)

## 3. Smoke Test the Swarm

From your MARVIN repo root, ask MARVIN:

> "Spin up the boys for a quick test: have 2 Gemini and 2 Codex workers each summarize what this repo is, then have the reviewer synthesize."

You should see MARVIN dispatch all workers in one message (background bash calls), wait, dispatch a Gemini reviewer, and present a synthesis. Failures land in `tools/boys-failures.log`.

---

## How It Runs Day-to-Day

Once set up, you don't invoke the boys manually — MARVIN dispatches them **proactively for any non-trivial task** per the protocol in `.claude/agents/the-boys.md`:

1. Workers (3+ Gemini, 2+ Codex) attack the problem from different angles — free
2. A fresh Gemini instance synthesizes all outputs — free
3. Claude (PM) reads only the synthesis, presents a recommendation
4. **You approve** → Claude applies the code

Two rules worth internalizing on day one:

- **Workers propose, never apply.** Nothing lands without your approval.
- **Never fake a CLI worker with the Agent tool.** The Agent tool only spawns Claude subagents — a subagent named "codex-1" is a Claude model burning your paid window while pretending to be free.
