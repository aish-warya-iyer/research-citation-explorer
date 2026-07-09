"""Start a .pipe file on RocketRide Cloud.

Bypasses a bug in the installed `rocketride` CLI/SDK (v1.3.0): `client.use()`
nests `project_id`/`source` inside the `pipeline` argument only, but the
server actually requires them as top-level `projectId`/`source` request
arguments -- without that, the server rejects every request with
"You must specifiy either token or project_id/source" regardless of what's
in the pipeline dict. This calls the lower-level `client.call('execute', ...)`
directly with the correct shape.
"""
import asyncio
import json
import sys
from rocketride.client import RocketRideClient
from common import load_env


async def start_pipeline(pipeline_path):
    env = load_env()
    with open(pipeline_path) as f:
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
            ttl=1200,
            pipelineTraceLevel="full",
        )
        print("Pipeline started.")
        print(json.dumps(body, indent=2))
        return body
    finally:
        await client.disconnect()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "summarize.pipe"
    asyncio.run(start_pipeline(path))
