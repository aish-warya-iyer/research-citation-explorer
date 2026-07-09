# Session Handoff — Research Citation & Idea Explorer

Paste this whole file (or just point Claude at it) at the start of a new session to resume.

## What this is
Hackathon project (HackwithBay 3.0) — Neo4j citation graph + RocketRide Cloud (summarization pipeline) + Butterbase (auth/collections/Stripe) + a thin FastAPI/vanilla-JS frontend.

## Where it lives
`~/Desktop/research-explorer` — a separate git repo from `~/Desktop/portfolio` (this session's default working directory). Always `cd` into it explicitly; this environment's Bash tool resets cwd between calls.

## How to run it
```bash
cd ~/Desktop/research-explorer
python3 -m uvicorn server:app --port 8000
```
Open `http://127.0.0.1:8000`. Log in with an existing test account or sign up fresh (test accounts below all use password `TestP@ssw0rd1`).

## Current state (all verified working)
- **Neo4j Aura**: 300 GNN papers loaded, citation/co-authorship edges, all 300 have real `Paper.summary` values (batch-generated via RocketRide, see below).
- **RocketRide Cloud**: `summarize.pipe` (webhook → `agent_rocketride` → `memory_internal` + `llm_openai_api` pointed at Butterbase's AI gateway) is deployed and genuinely working — but **only when invoked via the Python SDK's `client.chat(token, question)`**, not the public webhook HTTP endpoint (that endpoint accepts requests but silently never invokes the agent — undocumented platform bug, written up in `README.md`). `summarize_paper.py` is the clean, working entry point.
- **Butterbase** (app_id `app_574gyfj21hcu`): real per-user email/password auth, `collections`/`collection_papers` tables with RLS, named-collection model (not one-paper-per-collection), 3-free-collections paywall enforced via the `create-collection` function, Stripe Connect onboarded with a real Pro plan.
- **Frontend** (`server.py` + `static/index.html`): login/signup gate, search (Neo4j, bug-fixed — see below), save into a named collection, "my collections" view (expand/remove-paper/delete-collection), paywall modal, demo-safe "Upgrade" button. Visual design pass done (paper/citation-graph aesthetic: pale grey-blue bg, ink navy text, muted blue accent, Newsreader serif headings, node-dot+line motif per card).

## Known issues — read before touching these areas
1. **Stripe Connect is in LIVE mode**, not test mode. No documented per-app toggle exists (checked docs + dashboard). `stripe_checkout_real.py` has real, verified-working checkout code but is **deliberately not wired** to the frontend's "Upgrade" button — that button uses a safe service-role bypass insert instead (`server.py`, `/api/upgrade`, `_create_collection_bypassing_paywall`). **Do not wire the real Stripe flow to anything clickable without explicit user confirmation** — it would risk a real charge.
2. **RocketRide's public webhook doesn't work** for this pipeline — always drive it via `summarize_paper.py` / `client.chat()`, never `curl` the webhook URL directly for actual summarization.
3. RocketRide pipeline tasks are **deterministic per (project_id, source)** — starting the same pipeline twice without terminating the first errors with "Pipeline is already running." Terminate via `client.terminate(token)` first (see `generate_real_summaries.py` for the pattern).
4. Two real bugs already found and fixed this session, in case they resurface: (a) a Cypher `WHERE` right after `OPTIONAL MATCH` doesn't filter rows unless preceded by `WITH` — see `queries.py` `SEARCH_QUERY`; (b) HTML `onclick="..."` attributes break silently if you interpolate `JSON.stringify()` output (double-quoted) into a double-quoted attribute — use single-quoted `onclick='...'` when embedding `JSON.stringify()`.

## Do NOT do without being explicitly asked by name
- Do not run the Butterbase hackathon submission (`prep_and_submit_hackathon_entry` / `submit_suggestion`) — the user will ask for this as a separate, deliberate final step.
- Do not paste API keys/secrets into chat — they're already in `.env` (gitignored). If a key ever does leak into a chat message or tool output, flag it and suggest rotating it.

## Test accounts (Butterbase, app `app_574gyfj21hcu`)
- `test-researcher@example.com` / `TestP@ssw0rd1`
- `step1-test@example.com` / `TestP@ssw0rd1`
- `step2-test@example.com` / `TestP@ssw0rd1`
- (the user's own real account, `aish@gmail.com`, also exists — don't delete its data without asking)

## File map
- `common.py` — Neo4j driver + `.env` loader (shared by everything)
- `schema.py`, `ingest.py` — Neo4j schema + Semantic Scholar ingestion (one-time, already run)
- `queries.py` — Cypher queries used by the app (search, citation path, co-author centrality)
- `summarize.pipe` — the working RocketRide pipeline definition
- `summarize_paper.py` — call this to summarize a paper via RocketRide+Butterbase (the real, working path)
- `generate_real_summaries.py` — the batch script that populated all 300 `Paper.summary` values (already run; rerun only if you add new papers to the graph)
- `run_pipeline.py` — low-level RocketRide pipeline launcher (works around an SDK bug where `project_id`/`source` need to be top-level RPC args, not just nested in the pipeline dict)
- `server.py` — FastAPI backend (auth proxy, search, save/collections/paywall endpoints)
- `static/index.html` — the entire frontend (single page)
- `stripe_checkout_real.py` — real Stripe Checkout call, intentionally unwired (see Known Issues #1)
- `.env` — all credentials (Neo4j, Butterbase platform key + AI-gateway-scoped key, RocketRide API key) — gitignored
- `README.md` — deeper technical writeup of the RocketRide/Stripe investigations

## Natural next steps (not required, just where this could go)
- Wire `summarize_paper.py` for live summarization of genuinely new papers found via search (currently only pre-loaded papers have summaries)
- If time allows, investigate whether Butterbase support/Stripe dashboard offers a real test-mode path for Connect
- Prep for submission — **only when explicitly asked**
