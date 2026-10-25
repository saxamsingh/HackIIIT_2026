"""Create the TinyFish Monitors that feed Watch Mode.

    python -m app.scripts.create_monitors            # dry run: prints what would be created
    python -m app.scripts.create_monitors --apply    # creates them (live mode, a key, an https PUBLIC_BASE_URL)

Monitor API checked against docs.tinyfish.ai (CLAUDE.md section 6): `type` is "fetch" (a page) or "search"
(a query), each with a `schedule_cron` and an optional HTTPS `webhook_url`. The webhook is unsigned, so the
secret token rides in the URL and is redacted in everything this script prints."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from typing import Any

from .. import knowledge
from ..config import Settings, get_settings
from ..db import make_repository
from ..tinyfish import TinyFishClient, WebClientError, make_web_client


def webhook_url(settings: Settings) -> str | None:
    base = settings.public_base_url.rstrip("/")
    if not base:
        return None
    url = f"{base}/webhooks/tinyfish"
    return f"{url}?token={settings.tinyfish_webhook_token}" if settings.tinyfish_webhook_token else url


def redact(text: str) -> str:
    return re.sub(r"token=[^&\s]+", "token=***", text)


def build_specs(settings: Settings) -> list[dict[str, Any]]:
    hook = webhook_url(settings)
    return [
        {
            "name": "IMD district warnings",
            "type": "fetch",
            "config": {"url": knowledge.imd_url(settings), "format": "markdown"},
            "schedule_cron": "0 */3 * * *",
            "purpose": "A hail or heavy-rain warning names a district",
            "webhook_url": hook,
        },
        {
            "name": "New agriculture scheme notices",
            "type": "search",
            "config": {
                "query": f"new agriculture subsidy scheme notice for farmers {settings.demo_state}",
                "recency_minutes": 1440,
                "result_limit": 5,
            },
            "schedule_cron": "0 6 * * *",
            "purpose": "A new scheme or circular is announced",
            "webhook_url": hook,
        },
    ]


def problems(settings: Settings) -> list[str]:
    out = []
    if settings.tinyfish_mode != "live" or not settings.tinyfish_api_key:
        out.append("needs TINYFISH_MODE=live and TINYFISH_API_KEY")
    if not settings.public_base_url.startswith("https://"):
        out.append("needs PUBLIC_BASE_URL to be an https URL: TinyFish only calls HTTPS webhooks")
    if not settings.tinyfish_webhook_token:
        out.append("needs TINYFISH_WEBHOOK_TOKEN: the webhook is unsigned, so the token is its only protection")
    return out


async def apply(specs: list[dict[str, Any]], client: TinyFishClient) -> list[dict[str, Any]]:
    created = []
    for spec in specs:
        created.append(
            await client.create_monitor(
                spec["type"], spec["config"], spec["schedule_cron"], spec["webhook_url"],
                name=spec["name"], purpose=spec["purpose"],
            )
        )
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the Watch Mode monitors")
    parser.add_argument("--apply", action="store_true", help="really create them (default is a dry run)")
    args = parser.parse_args(argv)
    settings = get_settings()
    specs = build_specs(settings)

    for spec in specs:
        shown = {**spec, "webhook_url": redact(spec["webhook_url"] or "(none: set PUBLIC_BASE_URL)")}
        print(shown)
    if not args.apply:
        print("\ndry run: nothing was created. Add --apply to create these monitors.")
        return 0
    if issues := problems(settings):
        for issue in issues:
            print(f"cannot apply: {issue}", file=sys.stderr)
        return 2
    client = make_web_client(settings, make_repository(settings))
    assert isinstance(client, TinyFishClient)
    try:
        created = asyncio.run(apply(specs, client))
    except WebClientError as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1
    for item in created:
        print("created:", item.get("monitor", {}).get("id"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
