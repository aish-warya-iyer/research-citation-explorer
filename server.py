"""Local dev static file server.

The frontend (static/index.html) talks directly to Butterbase -- Auth API,
REST API (collections/collection_papers, RLS-scoped by the user's JWT), and
two Functions (search-papers, save-paper) -- for both local dev and the live
deployment at https://research-explorer.butterbase.dev. This file exists only
so `static/index.html` has somewhere to be served from locally; it proxies
nothing.

search-papers calls Neo4j Aura's HTTP Query API (Functions run in a JS
isolate runtime with no raw TCP/bolt socket support, so the Python
neo4j-driver used by queries.py/ingest.py can't run there -- only local
scripts use it). save-paper ports the old paywall-bypass logic: find-or-create
a collection by name, either via the real create-collection function (which
checks Butterbase's actual billing subscription) or, if the client has
clicked the demo "Upgrade" button, a plain RLS-scoped insert that skips the
quota check without touching live Stripe.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/", StaticFiles(directory="static", html=True), name="static")
