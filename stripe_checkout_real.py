"""Real Stripe Checkout integration via Butterbase Connect -- implemented and
verified working (see session transcript), but deliberately NOT wired to the
running demo server's /api/upgrade endpoint.

Why: Butterbase's Connect onboarding for this app (acct_1Tr4NO2Ej6WjxH6D)
came back issuing LIVE-mode Checkout sessions (session ids prefixed
`cs_live_`, not `cs_test_`), and there is no documented per-app or per-account
toggle to force test mode (checked butterbase_docs topics: billing,
integrations, platform -- no test_mode/livemode parameter on any Connect
endpoint). Wiring a real "Upgrade" button to this in a demo would risk an
actual charge on a real card, so server.py's /api/upgrade uses a
service-role bypass insert instead (see server.py docstring).

This script is the real thing: run it directly to generate an actual Stripe
Checkout URL for the Pro plan, confirming the Connect + plan integration is
genuinely functional end-to-end.
"""
import requests
from common import load_env

env = load_env()
BUTTERBASE_APP_ID = "app_574gyfj21hcu"
PRO_PLAN_ID = "bdb2cf6e-7f0b-44b4-8270-d5abef4951aa"
DEMO_USER_EMAIL = "test-researcher@example.com"
DEMO_USER_PASSWORD = "TestP@ssw0rd1"


def get_checkout_url():
    login = requests.post(
        f"https://api.butterbase.ai/auth/{BUTTERBASE_APP_ID}/login",
        json={"email": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD},
        timeout=15,
    )
    login.raise_for_status()
    token = login.json()["access_token"]

    resp = requests.post(
        f"https://api.butterbase.ai/v1/{BUTTERBASE_APP_ID}/billing/subscribe",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "planId": PRO_PLAN_ID,
            "successUrl": "https://research-explorer.butterbase.dev/success",
            "cancelUrl": "https://research-explorer.butterbase.dev/cancel",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    result = get_checkout_url()
    print("Checkout session created:", result["sessionId"])
    print("Mode:", "LIVE" if result["sessionId"].startswith("cs_live_") else "test")
    print("URL:", result["url"])
    print("\nNot opening this URL automatically -- see module docstring for why.")
