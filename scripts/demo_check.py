"""Walk the four demo paths against a running server and print PASS or FAIL for each (CLAUDE.md section 11).

    python scripts/demo_check.py --spawn                      # starts its own replay-mode server, no network
    python scripts/demo_check.py --base-url http://localhost:8000

--spawn works on a throwaway copy of knowledge/ in which the schemes are reviewed by "demo-check (automated,
not a human review)", so the real files are untouched. Against your own server the schemes check passes only
after a person has run `python -m app.cli review ...`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FARMER = "farmer_demo_1"


def check_sell(c: httpx.Client) -> str:
    before = c.get("/api/ledger", params={"farmer_id": FARMER}).json()["projected_rs"]
    r = c.post("/api/chat", json={"text": "Gehu kahan bechun? 20 quintal", "farmer_id": FARMER}).json()
    assert r["status"] == "answered" and r["agent"] == "sell", f"not answered: {r['status']} {r['reasons']}"
    options = r["data"]["options"]
    assert len(options) >= 3, "fewer than 3 mandis"
    assert all(e["source_url"] for e in r["evidence"]), "a price line has no source"
    assert r["data"]["msp"]["price_rs_per_qtl"], "no MSP line"
    after = c.get("/api/ledger", params={"farmer_id": FARMER}).json()["projected_rs"]
    assert after > before, "the ledger did not increase"
    best = r["data"]["best"]
    return f"{len(options)} mandis ranked, best {best['mandi']} at Rs {best['net_price']:g}, ledger +{after - before:g}"


def check_schemes(c: httpx.Client) -> str:
    r = c.get("/api/schemes", params={"farmer_id": FARMER}).json()
    if not r["schemes"]:
        raise AssertionError(r["note"] or "no schemes (has anyone reviewed them?)")
    eligible = [s for s in r["schemes"] if s["eligible"]]
    assert len(eligible) >= 2, f"only {len(eligible)} eligible"
    pdf = c.get(eligible[0]["packet_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), "packet PDF did not download"
    return f"{len(eligible)} eligible schemes, packet PDF downloads ({len(pdf.content)} bytes)"


def check_hail(c: httpx.Client) -> str:
    started = time.monotonic()
    r = c.post("/demo/replay-monitor", json={"fixture_name": "hail"})
    assert r.status_code == 200, f"{r.status_code}: {r.text[:120]} (already raised? use a fresh database)"
    alert = r.json()
    assert alert["type"] == "hail" and alert["claim_id"], "no alert or no claim prepared"
    assert any(a["id"] == alert["id"] for a in c.get("/api/alerts").json()), "alert not listed on Home"
    pdf = c.get(f"/files/dossier-{alert['claim_id']}.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), "dossier PDF missing"
    return f"alert raised, dossier PDF ready in {time.monotonic() - started:.1f}s"


def check_dose(c: httpx.Client) -> str:
    r = c.post("/api/chat", json={"text": "Chlorpyrifos kitna ml dalu?", "farmer_id": FARMER}).json()
    assert r["status"] == "escalated" and r["reasons"] == ["dose_question"], f"got {r['status']}"
    assert r["data"] == {} and r["evidence"] == [], "the response carries content it should have withheld"
    assert r["ticket_id"] and r["ticket_id"] in r["reply"], "no ticket in the hand-off"
    return f"escalated, ticket {r['ticket_id']}, no dose shown"


CHECKS = [
    ("a. WhatsApp/web: sell question -> ranked mandis + ledger up", check_sell),
    ("b. Schemes -> 2+ eligible -> packet PDF", check_schemes),
    ("c. Replayed hail warning -> alert + claim dossier PDF", check_hail),
    ("d. Dose question -> escalation, ticket, nothing shown", check_dose),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def spawn() -> tuple[subprocess.Popen, str, Path]:
    work = Path(tempfile.mkdtemp(prefix="khetkaaj-demo-"))
    knowledge = work / "knowledge"
    shutil.copytree(ROOT / "knowledge", knowledge)
    sys.path.insert(0, str(BACKEND))
    from app.config import Settings
    from app.schemes import load_schemes, review_scheme

    s = Settings(_env_file=None, knowledge_dir=knowledge)
    for scheme in load_schemes(s):
        review_scheme(s, scheme.id, "demo-check (automated, not a human review)")
    port = free_port()
    env = {
        **os.environ, "TINYFISH_MODE": "replay", "TINYFISH_API_KEY": "", "DB_BACKEND": "sqlite",
        "SQLITE_PATH": str(work / "demo.db"), "FILES_DIR": str(work / "files"), "CACHE_DIR": str(work / "cache"),
        "KNOWLEDGE_DIR": str(knowledge), "TWILIO_AUTH_TOKEN": "", "ANTHROPIC_API_KEY": "", "LLM_PHRASING": "0",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc, f"http://127.0.0.1:{port}", work


def wait_up(base: str, proc: subprocess.Popen | None) -> None:
    for _ in range(100):
        if proc is not None and proc.poll() is not None:
            raise SystemExit("the spawned server exited early")
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise SystemExit(f"{base} did not come up")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--spawn", action="store_true", help="start a private replay-mode server for the check")
    args = parser.parse_args()

    proc = work = None
    base = args.base_url
    if args.spawn:
        proc, base, work = spawn()
    try:
        wait_up(base, proc)
        health = httpx.get(f"{base}/health").json()
        print(f"server {base}  tinyfish_mode={health['tinyfish_mode']}  db={health['db_backend']}\n")
        failed = 0
        with httpx.Client(base_url=base, timeout=60) as c:
            for name, fn in CHECKS:
                try:
                    print(f"PASS  {name}\n        {fn(c)}")
                except (AssertionError, KeyError, httpx.HTTPError) as e:
                    failed += 1
                    print(f"FAIL  {name}\n        {type(e).__name__}: {e}")
        print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
        return 1 if failed else 0
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)
        if work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
