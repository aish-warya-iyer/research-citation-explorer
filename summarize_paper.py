"""Summarize a paper via the RocketRide Cloud pipeline (summarize.pipe), which
calls Butterbase's AI gateway through an agent_rocketride -> llm_openai_api chain.

Root cause of the earlier "silent failure" (documented in git history / session
transcript, kept here for reference):
1. RocketRide's `agent_rocketride` ("Wave") node requires a `memory_internal`
   control connection to function at all -- without one it fails internally
   with "wave agent requires a memory node to be connected", but that error
   is only surfaced through the proper `client.chat()` RPC, not through the
   public webhook HTTP endpoint (which silently no-ops instead).
2. The public webhook endpoint does not correctly route data into the
   "questions" lane at all -- even with the memory node fixed, invoking via
   a raw webhook POST still does not trigger the agent. `client.chat()` with
   a `Question` object, over the same WebSocket connection used to start the
   pipeline, is the actual supported mechanism for questions/answers lanes.

Usage: python3 summarize_paper.py
"""
import asyncio
import json
from rocketride.client import RocketRideClient
from rocketride.schema import Question
from common import load_env


async def summarize(title, abstract, ttl=300):
    env = load_env()
    with open("summarize.pipe") as f:
        pipeline = json.load(f)

    rocket_env = {k: v for k, v in env.items() if k.startswith("ROCKETRIDE_")}

    client = RocketRideClient(uri=env["ROCKETRIDE_URI"], auth=env["ROCKETRIDE_APIKEY"])
    await client.connect()
    try:
        body = await client.call(
            "execute",
            pipeline=pipeline,
            projectId=pipeline["project_id"],
            source=pipeline["source"],
            args=[],
            env=rocket_env,
            ttl=ttl,
        )
        token = body["token"]

        question = Question()
        question.addContext(f"Title: {title}\nAbstract: {abstract}")
        question.addQuestion(
            "Summarize the paper above in 2 sentences for a researcher. "
            "Use only the title and abstract given in the context -- do not look anything up."
        )

        response = await client.chat(token=token, question=question)
        return response["summary"][0]
    finally:
        await client.disconnect()


if __name__ == "__main__":
    result = asyncio.run(summarize(
        title="Graph Attention Networks",
        abstract=(
            "We present graph attention networks (GATs), novel neural network "
            "architectures that operate on graph-structured data, leveraging "
            "masked self-attentional layers to address the shortcomings of "
            "prior methods based on graph convolutions."
        ),
    ))
    print(result)
