"""Batch-generate real summaries for every paper in Neo4j via the RocketRide
Cloud pipeline (summarize.pipe -> agent_rocketride -> llm_openai_api ->
Butterbase AI gateway), and write them back onto Paper.summary in Neo4j.

Starts the pipeline once and reuses the same token/connection for every
paper (chat() calls are cheap RPCs over the existing WebSocket -- no need
to restart the pipeline per paper).

Usage: python3 generate_real_summaries.py
"""
import asyncio
import json
import sys
import time
from rocketride.client import RocketRideClient
from rocketride.schema import Question
from common import get_driver, load_env

BATCH_WRITE_EVERY = 10


def fetch_papers():
    driver = get_driver()
    try:
        with driver.session() as session:
            rows = session.run(
                "MATCH (p:Paper) RETURN p.paperId AS paperId, p.title AS title, p.abstract AS abstract"
            )
            return [dict(r) for r in rows]
    finally:
        driver.close()


def write_summaries(batch):
    driver = get_driver()
    try:
        with driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Paper {paperId: row.paperId})
                SET p.summary = row.summary
                """,
                rows=batch,
            )
    finally:
        driver.close()


async def summarize_one(client, token, title, abstract):
    question = Question()
    if abstract:
        question.addContext(f"Title: {title}\nAbstract: {abstract}")
        question.addQuestion(
            "Summarize the paper above in 2 sentences for a researcher browsing "
            "a citation graph. Use only the title and abstract given -- do not look anything up."
        )
    else:
        question.addContext(f"Title: {title}")
        question.addQuestion(
            "Based only on this paper title, write a 1-sentence guess at what "
            "the paper likely covers, for a researcher browsing a citation graph."
        )
    response = await client.chat(token=token, question=question)
    return response["summary"][0]


async def main():
    papers = fetch_papers()
    if len(sys.argv) > 1:
        papers = papers[: int(sys.argv[1])]
    print(f"{len(papers)} papers to summarize")

    env = load_env()
    with open("summarize.pipe") as f:
        pipeline = json.load(f)
    rocket_env = {k: v for k, v in env.items() if k.startswith("ROCKETRIDE_")}

    client = RocketRideClient(uri=env["ROCKETRIDE_URI"], auth=env["ROCKETRIDE_APIKEY"])
    await client.connect()

    pending_writes = []
    done = 0
    failed = []

    try:
        body = await client.call(
            "execute",
            pipeline=pipeline,
            projectId=pipeline["project_id"],
            source=pipeline["source"],
            args=[],
            env=rocket_env,
            ttl=3600,
        )
        token = body["token"]
        print("Pipeline started, token:", token)

        for i, p in enumerate(papers):
            try:
                summary = await summarize_one(client, token, p["title"], p["abstract"])
                pending_writes.append({"paperId": p["paperId"], "summary": summary})
                done += 1
            except Exception as e:
                print(f"  [{i+1}/{len(papers)}] FAILED ({p['title'][:50]}): {type(e).__name__} {e}")
                failed.append(p["paperId"])

            if len(pending_writes) >= BATCH_WRITE_EVERY:
                write_summaries(pending_writes)
                pending_writes = []

            if (i + 1) % 10 == 0 or i == len(papers) - 1:
                print(f"  [{i+1}/{len(papers)}] done={done} failed={len(failed)}")

        if pending_writes:
            write_summaries(pending_writes)

        try:
            await client.terminate(token)
        except Exception:
            pass
    finally:
        await client.disconnect()

    print(f"\nFinished: {done} summarized, {len(failed)} failed")
    if failed:
        print("Failed paperIds:", failed)


if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    print(f"Total time: {time.time() - start:.0f}s")
