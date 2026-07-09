# Research Citation & Idea Explorer

Live: https://research-explorer.butterbase.dev

## Stack
- **Neo4j Aura**: 300-paper "graph neural networks" citation graph (`ingest.py`, `schema.py`, `queries.py`) -- Cypher traversals for citation paths, co-authorship centrality, topic search.
- **Butterbase**: auth, `collections`/`collection_papers` tables with RLS (including a per-collection `notes` field), `create-collection` function enforcing a 3-collection free tier via a real billing-subscription check, Stripe Connect Pro plan, and two more Functions: `search-papers` (queries Neo4j) and `save-paper` (find-or-create collection + attach paper).
- **RocketRide Cloud**: webhook-triggered pipeline calling Butterbase's AI gateway (`summarize.pipe`).
- **Frontend**: `static/index.html` alone -- a pure static page that calls Butterbase's Auth API, REST API, and the two Functions above directly (RLS scopes every read/write to the caller's own JWT). No backend proxy in production. `server.py` is a two-line static file server that exists only for local dev convenience.

Run locally: `python3 -m uvicorn server:app --port 8000`, open `http://127.0.0.1:8000` -- it talks to the same live Butterbase backend as the deployed URL, so behavior is identical either way.

## Why there are two copies of the search/save logic

`queries.py` (Python, uses the `neo4j` bolt driver) is for the one-time ingestion/batch-summarization scripts run from a terminal. The deployed `search-papers` Function is a separate TypeScript port that calls Neo4j Aura's HTTP Query API instead, because Butterbase Functions run in a JS isolate runtime with no raw TCP/bolt socket support -- the Python driver simply can't run there. Same Cypher, two transports.

## RocketRide summarization pipeline (resolved)

`summarize.pipe` deploys to RocketRide Cloud: a webhook trigger feeds an `agent_rocketride` ("Wave") agent, which calls a `llm_openai_api` node pointed at Butterbase's AI gateway. `summarize_paper.py` drives it end-to-end and produces real summaries (verified: Butterbase AI-credit balance visibly decrements per call).

Two real platform bugs had to be found and worked around to get here:
1. **Undocumented required node**: `agent_rocketride` fails internally with `"wave agent requires a memory node to be connected"` if no `memory_internal` node is wired to its `memory` control port -- required even though nothing in the docs or the node's own config UI mentions it. Fixed by adding a `memory_internal` node with `"control": [{"classType": "memory", "from": "agent"}]`.
2. **The public webhook endpoint doesn't route into the `questions` lane at all.** Posting to the webhook HTTP URL is silently accepted (200 OK, task shows `completed`) but never advances past the trigger node and never invokes the agent -- with or without the memory fix. The actual working mechanism is the Python SDK's `client.chat(token, question)`, which sends a structured `Question` object over the same WebSocket connection used to start the pipeline. This is what `summarize_paper.py` uses.

**Practical implication**: any real "ingest a new paper" integration needs to drive this pipeline via the RocketRide Python SDK (`summarize_paper.py`), not a plain HTTP POST to the webhook URL -- despite the webhook being the pipeline's configured source node.

**How summaries get into the demo**: rather than calling the pipeline live on every search (slow, and pointless to re-summarize the same fixed corpus repeatedly), `generate_real_summaries.py` runs once as a batch job: it starts `summarize.pipe` a single time and reuses that one running task's `client.chat()` connection for all ~300 papers already loaded in Neo4j, writing each result onto `Paper.summary`. `queries.py`'s search query returns `p.summary` directly, so `/api/papers` and the frontend need no separate summary-lookup layer -- every paper search result carries a real, RocketRide-generated summary, labeled "AI-generated summary (RocketRide + Butterbase gateway)" in the UI. `summarize_paper.py` remains available to call directly for a genuinely new paper not yet in the graph (e.g. from a fresh Semantic Scholar ingest) -- optional, not required for the current demo path.

(The earlier `demo_summaries.json` / `generate_demo_summaries.py` stand-in, from before this pipeline was fixed, has been removed -- superseded by the above.)

## Known issue: Stripe Connect live mode

Butterbase's Stripe Connect onboarding for this app issued a **live-mode** Checkout session (`cs_live_...`) with no documented per-app or per-account test-mode toggle (checked `billing`, `integrations`, and `platform` docs topics, plus the dashboard). `stripe_checkout_real.py` contains the real, verified-working Checkout session creation call -- confirmed functional, but deliberately not wired to the frontend's "Upgrade" button to avoid risking a real charge during development or demo. The frontend's upgrade flow instead sets a local flag that the `save-paper` Function honors as `bypassPaywall`: it does a plain RLS-scoped insert (`user_id = current_user_id()`) that skips `create-collection`'s quota check without touching real billing -- same demo-safe behavior as before, now living server-side in the Function instead of the old FastAPI proxy.
