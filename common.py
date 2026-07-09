import os
from neo4j import GraphDatabase


def load_env(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def get_driver():
    env = load_env()
    uri = env.get("NEO4J_URI")
    user = env.get("NEO4J_USERNAME")
    password = env.get("NEO4J_PASSWORD")
    missing = [k for k, v in {"NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing .env values: {', '.join(missing)}")
    return GraphDatabase.driver(uri, auth=(user, password))
