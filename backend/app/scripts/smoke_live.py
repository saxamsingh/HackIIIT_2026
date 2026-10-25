"""Live smoke test: one Fetch and one short Agent run against real TinyFish.

    TINYFISH_MODE=live TINYFISH_API_KEY=... python -m app.scripts.smoke_live

Prints the streaming_url as soon as it arrives, the result, the steps taken, and what the run cost, measured
as the change in the wallet balance (TinyFish does not put a cost on the run itself). Costs a few cents."""

from __future__ import annotations

import asyncio
import sys
import time

from ..config import get_settings
from ..db import make_repository
from ..tinyfish import AgentEvent, TinyFishClient, make_web_client

URL = "https://example.com/"
GOAL = "Return the text of the page's main heading as JSON with the key 'title'."
SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}


def _show(event: AgentEvent) -> None:
    if event.type == "STREAMING_URL":
        print(f"  streaming_url: {event.streaming_url}", flush=True)
    elif event.type == "PROGRESS":
        print(f"  step: {event.purpose}", flush=True)


async def run() -> int:
    settings = get_settings()
    if settings.tinyfish_mode != "live" or not settings.tinyfish_api_key:
        print("Set TINYFISH_MODE=live and TINYFISH_API_KEY (in .env or the environment) to run the live smoke test.")
        return 2
    repo = make_repository(settings)
    client = make_web_client(settings, repo)
    assert isinstance(client, TinyFishClient)

    before = await client.wallet_balance()
    print(f"wallet balance before: {before if before is not None else 'unavailable'}")

    print(f"\n1. Fetch {URL}")
    started = time.monotonic()
    fetched = await client.fetch([URL], purpose="KhetKaaj smoke test", fresh=True)
    page = fetched.results[0] if fetched.results else None
    print(f"  {len(page.text or '')} characters in {time.monotonic() - started:.1f}s; errors: {fetched.errors}")

    print(f"\n2. Agent run on {URL}")
    started = time.monotonic()
    run = await client.run_agent(URL, GOAL, SCHEMA, on_event=_show)
    elapsed = time.monotonic() - started
    print(f"  status: {run.status}  run_id: {run.run_id}")
    print(f"  result: {run.result}")
    print(f"  steps: {run.num_of_steps}  time: {elapsed:.1f}s  streaming_url: {run.streaming_url}")

    after = await client.wallet_balance()
    if before is not None and after is not None:
        print(f"\nwallet balance after: {after}  ->  these two calls cost {before - after:.4f}")
    print(f"budget used: {client.budget.usage()}")
    return 0 if run.status == "COMPLETED" else 1


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
