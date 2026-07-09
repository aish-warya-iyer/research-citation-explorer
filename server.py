"""Backend for the demo: Neo4j paper search + Butterbase auth/collections/paywall.

Auth model: real per-user Butterbase auth. The frontend logs in (or signs up)
against Butterbase directly through this backend, gets a JWT back, and sends
it as `Authorization: Bearer <token>` on every subsequent request. This
backend forwards that JWT to Butterbase for collections/save calls -- it does
not hold a fixed demo session anymore. `require_auth` gates search/save/
collections; requests without a valid-looking Authorization header are
rejected with 401.

User id is read directly off the JWT payload (base64-decoded, not
signature-verified) purely to know whose collections to bypass-insert into
on `/api/upgrade` -- the actual authorization for every real data operation
still happens on Butterbase's side via the forwarded JWT.

Upgrade path: the real Stripe Checkout flow (tested and working, see
stripe_checkout_real.py) is deliberately NOT wired to the /api/upgrade
endpoint below, because Butterbase's Connect onboarding came back in Stripe
LIVE mode with no documented per-app test-mode toggle. Wiring a real "Upgrade"
click to it would risk a real charge. Instead /api/upgrade flips an in-memory
per-user flag and the next save bypasses the paywall via a direct service-key
insert (butterbase_service role, RLS-bypassing) -- functionally identical to
what happens once a real subscription is active, without touching live Stripe.
"""
import base64
import json

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from common import get_driver, load_env
from queries import search_papers

env = load_env()

BUTTERBASE_APP_ID = "app_574gyfj21hcu"
BUTTERBASE_API_BASE = f"https://api.butterbase.ai/v1/{BUTTERBASE_APP_ID}"
BUTTERBASE_AUTH_BASE = f"https://api.butterbase.ai/auth/{BUTTERBASE_APP_ID}"

app = FastAPI()
neo4j_driver = get_driver()

pro_users = set()  # user_ids that clicked "Upgrade to Pro" this server session


@app.exception_handler(requests.exceptions.HTTPError)
async def handle_butterbase_http_error(request: Request, exc: requests.exceptions.HTTPError):
    # A forwarded user JWT can expire mid-session (15 min default lifetime) --
    # without this handler, any raise_for_status() call would surface as an
    # opaque 500 instead of a 401 the frontend already knows to react to
    # (redirect back to the login screen).
    status = exc.response.status_code if exc.response is not None else 502
    if status == 401:
        return JSONResponse({"error": "Session expired, please log in again"}, status_code=401)
    return JSONResponse({"error": "Upstream error from Butterbase", "detail": str(exc)}, status_code=502)


def require_auth(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    return authorization[len("Bearer "):]


def user_id_from_jwt(token: str) -> str:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    return payload["sub"]


@app.post("/api/auth/signup")
async def api_signup(request: Request):
    body = await request.json()
    resp = requests.post(
        f"{BUTTERBASE_AUTH_BASE}/signup",
        json={"email": body.get("email"), "password": body.get("password")},
        timeout=15,
    )
    if not resp.ok:
        return JSONResponse(resp.json(), status_code=resp.status_code)
    # Butterbase signup doesn't return a token; log in immediately after so
    # the frontend gets a usable session without a separate verification step.
    login_resp = requests.post(
        f"{BUTTERBASE_AUTH_BASE}/login",
        json={"email": body.get("email"), "password": body.get("password")},
        timeout=15,
    )
    login_resp.raise_for_status()
    return login_resp.json()


@app.post("/api/auth/login")
async def api_login(request: Request):
    body = await request.json()
    resp = requests.post(
        f"{BUTTERBASE_AUTH_BASE}/login",
        json={"email": body.get("email"), "password": body.get("password")},
        timeout=15,
    )
    if not resp.ok:
        return JSONResponse(resp.json(), status_code=resp.status_code)
    return resp.json()


@app.post("/api/auth/logout")
def api_logout(token: str = Depends(require_auth)):
    try:
        requests.post(
            f"{BUTTERBASE_AUTH_BASE}/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except requests.RequestException:
        pass
    return {"ok": True}


@app.get("/api/papers")
def api_search(q: str = "", token: str = Depends(require_auth)):
    # Papers carry a real summary (Paper.summary in Neo4j) generated in batch
    # via the RocketRide Cloud pipeline calling Butterbase's AI gateway --
    # see generate_real_summaries.py and README.
    with neo4j_driver.session() as session:
        rows = search_papers(session, q, limit=20)
    return [dict(r) for r in rows]


DEFAULT_COLLECTION_NAME = "My Reading List"


@app.post("/api/save")
async def api_save(request: Request, token: str = Depends(require_auth)):
    body = await request.json()
    paper_id = body.get("paperId")
    title = body.get("title")
    collection_name = (body.get("collectionName") or "").strip() or DEFAULT_COLLECTION_NAME
    if not paper_id or not title:
        return JSONResponse({"error": "paperId and title required"}, status_code=400)

    user_id = user_id_from_jwt(token)

    existing = _find_collection_by_name(token, collection_name)
    if existing:
        collection = existing
    elif user_id in pro_users:
        collection = _create_collection_bypassing_paywall(user_id, collection_name)
    else:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = requests.post(
            f"{BUTTERBASE_API_BASE}/fn/create-collection",
            headers=headers,
            json={"name": collection_name},
            timeout=20,
        )
        if resp.status_code == 402:
            return JSONResponse(resp.json(), status_code=402)
        resp.raise_for_status()
        collection = resp.json()

    _attach_paper_to_collection(token, collection["id"], paper_id, title)
    return collection


@app.post("/api/upgrade")
def api_upgrade(token: str = Depends(require_auth)):
    """Demo-safe 'upgrade': flips a local per-user flag instead of charging a
    real card. See module docstring for why this doesn't call real Stripe Checkout."""
    pro_users.add(user_id_from_jwt(token))
    return {"is_pro": True}


@app.get("/api/collections")
def api_collections(token: str = Depends(require_auth)):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{BUTTERBASE_API_BASE}/collections",
        headers=headers,
        params={"order": "created_at.desc"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@app.get("/api/collections/{collection_id}/papers")
def api_collection_papers(collection_id: str, token: str = Depends(require_auth)):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{BUTTERBASE_API_BASE}/collection_papers",
        headers=headers,
        params={"collection_id": f"eq.{collection_id}", "order": "added_at.desc"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@app.patch("/api/collections/{collection_id}")
async def api_update_collection_notes(collection_id: str, request: Request, token: str = Depends(require_auth)):
    body = await request.json()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    resp = requests.patch(
        f"{BUTTERBASE_API_BASE}/collections/{collection_id}",
        headers=headers,
        json={"notes": body.get("notes", "")},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if isinstance(rows, list) else rows


@app.delete("/api/collections/{collection_id}")
def api_delete_collection(collection_id: str, token: str = Depends(require_auth)):
    # Deletes the whole collection (cascades to its collection_papers rows),
    # freeing up a slot in the 3-free-collections quota -- the paywall check
    # counts current rows, not lifetime creates.
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.delete(
        f"{BUTTERBASE_API_BASE}/collections/{collection_id}",
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return {"ok": True}


@app.delete("/api/collection_papers/{item_id}")
def api_remove_paper(item_id: str, token: str = Depends(require_auth)):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.delete(
        f"{BUTTERBASE_API_BASE}/collection_papers/{item_id}",
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return {"ok": True}


def _find_collection_by_name(token, name):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{BUTTERBASE_API_BASE}/collections",
        headers=headers,
        params={"name": f"eq.{name}", "limit": 1},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def _create_collection_bypassing_paywall(user_id, name):
    """Service-role insert (RLS-bypassing), used only once the user is in
    pro_users -- simulates what create-collection does for a real subscriber."""
    headers = {
        "Authorization": f"Bearer {env['BUTTERBASE_API_KEY']}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{BUTTERBASE_API_BASE}/collections",
        headers=headers,
        json={"user_id": user_id, "name": name},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _attach_paper_to_collection(token, collection_id, paper_id, title):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"{BUTTERBASE_API_BASE}/collection_papers",
        headers=headers,
        json={"collection_id": collection_id, "paper_id": paper_id, "title": title},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    # Avoid stale-JS confusion during active dev -- browsers otherwise cache
    # static assets aggressively, making fixed bugs look unfixed after a
    # plain reload.
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static") or not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/", StaticFiles(directory="static", html=True), name="static")
