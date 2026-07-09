import sys
import time
import requests
from common import get_driver

TOPIC = "graph neural networks"
TARGET_COUNT = 300
SEARCH_FIELDS = "paperId,title,abstract,year,venue,citationCount,referenceCount,fieldsOfStudy,authors"
BULK_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
BATCH_CHUNK_SIZE = 100


def fetch_papers(topic, target_count):
    params = {
        "query": topic,
        "fields": SEARCH_FIELDS,
        "sort": "citationCount:desc",
    }
    resp = requests.get(BULK_SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    papers = payload.get("data", [])
    print(f"Bulk search returned {len(papers)} papers (of {payload.get('total')} total matches); taking top {target_count}.")
    return papers[:target_count]


def fetch_references(paper_ids):
    """Look up references separately -- the bulk search endpoint's `references`
    field expansion is broken for real (non-oversized) queries, so we use the
    batch endpoint instead, which handles nested fields correctly."""
    refs_by_id = {}
    for i in range(0, len(paper_ids), BATCH_CHUNK_SIZE):
        chunk = paper_ids[i:i + BATCH_CHUNK_SIZE]
        resp = requests.post(
            BATCH_URL,
            params={"fields": "paperId,references.paperId"},
            json={"ids": chunk},
            timeout=30,
        )
        if resp.status_code == 429:
            print("Rate limited on batch call, sleeping 5s...")
            time.sleep(5)
            resp = requests.post(
                BATCH_URL,
                params={"fields": "paperId,references.paperId"},
                json={"ids": chunk},
                timeout=30,
            )
        resp.raise_for_status()
        for entry in resp.json():
            if entry and entry.get("paperId"):
                refs_by_id[entry["paperId"]] = entry.get("references") or []
        print(f"Fetched references for {min(i + BATCH_CHUNK_SIZE, len(paper_ids))}/{len(paper_ids)} papers...")
        time.sleep(0.5)
    return refs_by_id


def load_into_neo4j(papers, refs_by_id, topic):
    driver = get_driver()
    try:
        with driver.session() as session:
            session.run("MERGE (:Topic {name: $topic})", topic=topic)

            paper_rows = []
            author_edges = []
            for p in papers:
                if not p or not p.get("paperId"):
                    continue
                paper_rows.append({
                    "paperId": p["paperId"],
                    "title": p.get("title"),
                    "abstract": p.get("abstract"),
                    "year": p.get("year"),
                    "venue": p.get("venue"),
                    "citationCount": p.get("citationCount"),
                    "referenceCount": p.get("referenceCount"),
                    "fieldsOfStudy": p.get("fieldsOfStudy") or [],
                })
                for a in (p.get("authors") or []):
                    if a.get("authorId"):
                        author_edges.append({
                            "paperId": p["paperId"],
                            "authorId": a["authorId"],
                            "name": a.get("name"),
                        })

            session.run(
                """
                UNWIND $rows AS row
                MERGE (p:Paper {paperId: row.paperId})
                SET p.title = row.title,
                    p.abstract = row.abstract,
                    p.year = row.year,
                    p.venue = row.venue,
                    p.citationCount = row.citationCount,
                    p.referenceCount = row.referenceCount,
                    p.fieldsOfStudy = row.fieldsOfStudy
                WITH p
                MATCH (t:Topic {name: $topic})
                MERGE (p)-[:IN_TOPIC]->(t)
                """,
                rows=paper_rows, topic=topic,
            )
            print(f"Loaded {len(paper_rows)} Paper nodes.")

            session.run(
                """
                UNWIND $rows AS row
                MERGE (a:Author {authorId: row.authorId})
                SET a.name = row.name
                WITH a, row
                MATCH (p:Paper {paperId: row.paperId})
                MERGE (a)-[:AUTHORED]->(p)
                """,
                rows=author_edges,
            )
            print(f"Loaded {len(author_edges)} AUTHORED edges.")

            citation_rows = []
            for citing_id, refs in refs_by_id.items():
                for ref in refs:
                    if ref and ref.get("paperId"):
                        citation_rows.append({"citing": citing_id, "cited": ref["paperId"]})

            result = session.run(
                """
                UNWIND $rows AS row
                MATCH (citing:Paper {paperId: row.citing})
                MATCH (cited:Paper {paperId: row.cited})
                MERGE (citing)-[:CITES]->(cited)
                RETURN count(*) AS created
                """,
                rows=citation_rows,
            )
            created = result.single()["created"]
            print(f"Loaded {created} CITES edges (within scoped set, out of {len(citation_rows)} candidate references).")
    finally:
        driver.close()


if __name__ == "__main__":
    print(f"Fetching ~{TARGET_COUNT} papers for topic: {TOPIC}")
    papers = fetch_papers(TOPIC, TARGET_COUNT)
    print(f"Total fetched: {len(papers)}")
    if not papers:
        print("No papers fetched, aborting.")
        sys.exit(1)

    paper_ids = [p["paperId"] for p in papers if p and p.get("paperId")]
    print("Fetching reference lists via batch endpoint...")
    refs_by_id = fetch_references(paper_ids)

    load_into_neo4j(papers, refs_by_id, TOPIC)
    print("Done.")
