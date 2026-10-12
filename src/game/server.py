"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: Needle -- the game server. Serves the page and a small JSON API.

The browser never sees labels or detector output until the player submits:
GET /series sends the values only, and the reveal comes back from POST
/submit, which also scores and logs the play. So the rules live in Python
(scoring.py), next to the analysis, not in the page.

    GET  /api/stats                         start screen and leaderboard
    POST /api/round              {nick}     start a round of six
    GET  /api/round/{rid}/{i}               series i of the round, values only
    POST /api/round/{rid}/{i}/submit        {ranges, nothing, elapsed_ms, view}
    POST /api/round/{rid}/{i}/feedback      {answer: see | cannot | else}
    POST /api/round/{rid}/finish            totals, rank on the board

Run:
    python src/game/make_dev_pack.py        # once, for the synthetic pack
    python src/game/server.py               # http://localhost:8000
    python src/game/server.py --pack data/game/tsb-ad --db data/game/icde.sqlite
"""

import argparse
import json
import random
import re
import sys
import uuid
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pack import Pack, load_pack  # noqa: E402
from scoring import DETECTOR_RULE, score_series  # noqa: E402
from store import Store  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB = Path(__file__).resolve().parent / "web"

# One round: two easy, two medium, one unsolved, one decoy, in random order.
ROUND_MIX = ["easy", "easy", "medium", "medium", "unsolved", "decoy"]

TIER_NOTE = {
    "easy": "Most of the detector team catches this one.",
    "medium": "Only some detectors catch this one.",
    "unsolved": "Even the best detector in the benchmark misses this one.",
    "decoy": "Some series are clean on purpose.",
}

ANSWERS = {"see", "cannot", "else"}


def pick_round(pack: Pack, rng: random.Random, mix=ROUND_MIX) -> list[int]:
    """One series per slot of the mix, no repeats. A tier that runs short is
    filled from whatever is left, so a small pack still plays."""
    pool = {t: rng.sample(ids, len(ids)) for t, ids in pack.by_tier().items()}
    chosen = []
    for tier in mix:
        if pool.get(tier):
            chosen.append(pool[tier].pop())
    rest = [i for ids in pool.values() for i in ids]
    rng.shuffle(rest)
    while len(chosen) < len(mix) and rest:
        chosen.append(rest.pop())
    rng.shuffle(chosen)
    return chosen


def clean_nick(nick) -> str:
    nick = re.sub(r"[^A-Z0-9 _.\-]", "", str(nick or "").upper()).strip()[:12]
    return nick or "ANON"


def create_app(pack_path: Path, db_path: Path, today_only: bool = True, seed: int | None = None):
    pack = load_pack(pack_path)
    store = Store(db_path)
    rng = random.Random(seed)

    def get_round(rid: str) -> dict:
        row = store.db.execute("SELECT * FROM rounds WHERE id = ?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such round")
        return {"id": rid, "nick": row["nick"], "series": json.loads(row["series"])}

    def get_series(rnd: dict, idx: int):
        if not 0 <= idx < len(rnd["series"]):
            raise HTTPException(404, "No such series in this round")
        return pack.series[rnd["series"][idx]]

    async def body(request: Request) -> dict:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "Expected a JSON body")
        if not isinstance(data, dict):
            raise HTTPException(400, "Expected a JSON object")
        return data

    def board_payload() -> dict:
        return {
            "stats": store.stats(today_only),
            "leaderboard": store.leaderboard(8, today_only),
            "team_size": len(pack.detectors),
            "round_size": len(ROUND_MIX),
        }

    async def stats(request: Request):
        return JSONResponse(board_payload())

    async def new_round(request: Request):
        data = await body(request)
        rid = uuid.uuid4().hex
        nick = clean_nick(data.get("nick"))
        series = pick_round(pack, rng)
        store.new_round(rid, nick, pack.name, series)
        return JSONResponse({"round_id": rid, "nick": nick, "count": len(series),
                             "team_size": len(pack.detectors)})

    async def series(request: Request):
        rnd = get_round(request.path_params["rid"])
        idx = request.path_params["idx"]
        s = get_series(rnd, idx)
        return JSONResponse({"idx": idx, "label": f"SERIES {s.id}", "n": s.n, "values": s.values})

    async def submit(request: Request):
        rnd = get_round(request.path_params["rid"])
        idx = request.path_params["idx"]
        s = get_series(rnd, idx)
        data = await body(request)
        nothing = bool(data.get("nothing"))
        ranges = [] if nothing else data.get("ranges") or []
        try:
            ranges = [[float(r[0]), float(r[1])] for r in ranges][:5]
        except (TypeError, ValueError, IndexError):
            raise HTTPException(400, "ranges must be a list of [start, end] pairs")

        result = score_series(ranges, s.labels, s.detectors, s.n)
        elapsed = data.get("elapsed_ms")
        store.log_play(rnd["id"], idx, s.id, s.tier, nothing, result,
                       int(elapsed) if isinstance(elapsed, (int, float)) else None,
                       {**(data.get("view") if isinstance(data.get("view"), dict) else {}),
                        "det_rule": DETECTOR_RULE})

        you, det = result["you"], result["det"]
        team = [{**d, "score": src["score"]} for d, src in zip(result["detectors"], s.detectors)]
        return JSONResponse({
            "idx": idx, "label": f"SERIES {s.id}", "n": s.n,
            "tier": s.tier, "tier_note": TIER_NOTE[s.tier],
            "labels": s.labels,
            "team_score": result["team_score"], "team_threshold": result["team_threshold"],
            "ranges": result["ranges"], "det_ranges": result["det_ranges"],
            "you": {k: you[k] for k in ("hits", "false_alarms", "missed", "clean", "points")},
            "det": {k: det[k] for k in ("hits", "false_alarms", "missed", "clean", "points")},
            "you_hits": you["label_hits"], "det_hits": det["label_hits"],
            "outcome": result["outcome"],
            "you_result": result["you_result"], "det_result": result["det_result"],
            "you_text": result["you_text"], "det_text": result["det_text"],
            "verdict": result["verdict"], "verdict_sub": result["verdict_sub"],
            "detectors": team, "caught": sum(d["caught"] for d in team),
        })

    async def feedback(request: Request):
        rnd = get_round(request.path_params["rid"])
        idx = request.path_params["idx"]
        s = get_series(rnd, idx)
        answer = (await body(request)).get("answer")
        if answer not in ANSWERS:
            raise HTTPException(400, f"answer must be one of {sorted(ANSWERS)}")
        store.log_feedback(rnd["id"], idx, s.id, answer)
        return JSONResponse({"ok": True})

    async def finish(request: Request):
        rnd = get_round(request.path_params["rid"])
        totals = store.finish_round(rnd["id"])
        board = board_payload()
        rank = next((k for k, r in enumerate(board["leaderboard"]) if r["round_id"] == rnd["id"]), None)
        return JSONResponse({**totals, "rank": rank, **board})

    async def index(request: Request):
        return FileResponse(WEB / "index.html")

    app = Starlette(routes=[
        Route("/", index),
        Route("/api/stats", stats),
        Route("/api/round", new_round, methods=["POST"]),
        Route("/api/round/{rid}/finish", finish, methods=["POST"]),
        Route("/api/round/{rid}/{idx:int}", series),
        Route("/api/round/{rid}/{idx:int}/submit", submit, methods=["POST"]),
        Route("/api/round/{rid}/{idx:int}/feedback", feedback, methods=["POST"]),
        Mount("/static", StaticFiles(directory=WEB), name="static"),
    ])

    # The page is a handful of small files: make the browser recheck them on
    # every load (a 304 when unchanged), so an update never runs half old code.
    async def no_stale_files(scope, receive, send):
        async def send_no_cache(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-cache")]
            await send(message)
        page = scope["type"] == "http" and not scope["path"].startswith("/api/")
        await app(scope, receive, send_no_cache if page else send)

    return no_stale_files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack", type=Path, default=REPO_ROOT / "data" / "game" / "dev")
    ap.add_argument("--db", type=Path, default=REPO_ROOT / "data" / "game" / "plays.sqlite")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--all-time", action="store_true",
                    help="leaderboard and stats over every day, not just today")
    args = ap.parse_args()

    import uvicorn
    app = create_app(args.pack, args.db, today_only=not args.all_time)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
