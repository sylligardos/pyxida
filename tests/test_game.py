"""Needle: scoring rules, the dev pack, and the server API end to end.

Runs without the benchmark: the server is tested on the synthetic dev pack.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1] / "game"
sys.path.insert(0, str(GAME))

from scoring import (clean_ranges, detector_caught, evaluate, labels_to_ranges,  # noqa: E402
                     result_key, score_series, threshold_ranges)


# --------------------------------------------------------------------------
# Ranges
# --------------------------------------------------------------------------

def test_clean_ranges_clips_orders_and_merges():
    assert clean_ranges([[50, 40], [45, 60], [-5, 3], [98, 120], [200, 300]], 100) == \
        [[0, 3], [40, 60], [98, 99]]


def test_clean_ranges_merges_touching():
    assert clean_ranges([[0, 4], [5, 9]], 20) == [[0, 9]]


def test_labels_to_ranges():
    y = np.zeros(20)
    y[3:6] = 1
    y[10] = 1
    y[19] = 1
    assert labels_to_ranges(y) == [[3, 5], [10, 10], [19, 19]]
    assert labels_to_ranges(np.zeros(5)) == []


# --------------------------------------------------------------------------
# Hits and false alarms
# --------------------------------------------------------------------------

def test_hits_count_per_anomaly_not_per_range():
    ev = evaluate([[10, 12], [13, 15], [16, 18]], [[11, 17]])
    assert (ev["hits"], ev["false_alarms"], ev["points"]) == (1, 0, 1)


def test_false_alarm_and_partial():
    labels = [[10, 20], [50, 60], [80, 85]]
    ev = evaluate([[15, 16], [55, 70], [30, 31]], labels)
    assert ev["hits"] == 2 and ev["false_alarms"] == 1 and ev["missed"] == 1
    assert ev["points"] == 1
    assert ev["label_hits"] == [True, True, False]
    assert result_key(ev, 3) == "partial"


def test_decoy_clean_and_bait():
    assert evaluate([], [])["points"] == 1
    bait = evaluate([[3, 4]], [])
    assert bait["points"] == -1 and result_key(bait, 0) == "false alarm"


def test_missed_is_zero():
    ev = evaluate([], [[5, 6]])
    assert ev["points"] == 0 and result_key(ev, 1) == "missed"


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------

def test_threshold_is_mean_plus_three_std():
    s = np.zeros(1000)
    s[100:110] = 1.0
    s[500:505] = 0.9
    assert threshold_ranges(s) == [[100, 109], [500, 504]]
    # Lower bump below mean + 3 std: not flagged.
    s[800:803] = 0.2
    assert [800, 802] not in threshold_ranges(s)


def test_threshold_groups_nearby_points():
    s = np.zeros(2000)
    s[[300, 302, 305, 309]] = 1.0          # within n // 200 = 10 of each other
    s[900] = 1.0
    assert threshold_ranges(s) == [[300, 309], [900, 900]]


def test_flat_score_flags_nothing():
    assert threshold_ranges(np.ones(500)) == []


def team(*scores):
    return [{"name": f"D{k}", "score": sc} for k, sc in enumerate(scores)]


def test_detectors_ignore_what_the_player_marked():
    s = np.zeros(500)
    s[200:205] = 1
    for ranges in ([], [[0, 10]], [[0, 10], [50, 60], [300, 400]]):
        assert score_series(ranges, [[201, 202]], team(s), 500)["det_ranges"] == [[200, 204]]


def test_decoy_bait():
    s = np.zeros(500)
    s[200:205] = 1
    r = score_series([], [], team(s), 500)                # decoy, player said nothing
    assert r["you"]["points"] == 1 and r["det"]["points"] == -1
    assert r["outcome"] == "you" and r["verdict"] == "NOTHING TO FIND"


def test_detector_caught():
    s = np.zeros(300)
    s[100:103] = 1
    assert detector_caught(s, [[101, 101]])
    assert not detector_caught(s, [[200, 210]])
    assert not detector_caught(s, [])


def test_verdicts():
    s = np.zeros(300)
    s[10:20] = 1
    assert score_series([[150, 160]], [[150, 155]], team(s), 300)["verdict"].startswith("YOU FOUND IT")
    assert score_series([[200, 210]], [[10, 15]], team(s), 300)["verdict"].startswith("THE DETECTORS FOUND IT")
    assert score_series([[200, 210]], [[250, 260]], team(s), 300)["verdict"] == "NOBODY FOUND THIS ONE"
    assert score_series([[12, 14]], [[10, 15]], team(s), 300)["verdict"] == "EVERYONE GOT THIS ONE"


def test_average_can_miss_what_one_detector_caught():
    """Four detectors agree on a wrong spot, one catches the anomaly: the team
    average misses it, and the sub-line says the lone one caught it."""
    hit, off = np.zeros(300), np.zeros(300)
    hit[10:20] = 1
    off[200:210] = 1
    r = score_series([], [[10, 15]], team(off, off, off, off, hit), 300)
    assert [d["caught"] for d in r["detectors"]] == [False] * 4 + [True]
    assert r["det_ranges"] == [[200, 209]]
    assert r["verdict"] == "NOBODY FOUND THIS ONE"
    assert "The detectors missed it; they raised one false alarm, though D4 alone crossed its line." in r["verdict_sub"]
    assert len(r["team_score"]) == 300 and r["team_threshold"] is not None


def test_pooled_rule_counts_every_detector():
    from scoring import detector_flags
    hit, off = np.zeros(300), np.zeros(300)
    hit[10:20] = 1
    off[200:210] = 1
    each, side = detector_flags(team(off, hit), [[10, 15]], 300, rule="pooled")
    assert side["flags"] == [[10, 19], [200, 209]] and side["score"] is None
    with pytest.raises(ValueError):
        detector_flags(team(off), [], 300, rule="vote")


# --------------------------------------------------------------------------
# Dev pack and server
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    pytest.importorskip("starlette")
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    import make_dev_pack
    from pack import write_pack
    from server import create_app

    root = tmp_path_factory.mktemp("needle")
    write_pack(root / "pack", "test", make_dev_pack.DETECTORS, make_dev_pack.build())
    return TestClient(create_app(root / "pack", root / "plays.sqlite", seed=0))


def test_dev_pack_tiers_behave():
    import make_dev_pack
    from pack import TIERS
    series = make_dev_pack.build()
    assert {s.tier for s in series} == set(TIERS)
    for s in series:
        assert 1000 <= s.n <= 10000
        caught = sum(detector_caught(d["score"], s.labels) for d in s.detectors)
        if s.tier == "easy":
            assert caught >= 3, (s.id, caught)
        if s.tier in ("unsolved", "decoy"):
            assert caught == 0, (s.id, caught)
        assert bool(s.labels) == (s.tier != "decoy")


def test_full_round(client):
    st = client.get("/api/stats").json()
    assert st["stats"]["plays"] == 0 and st["leaderboard"] == []

    r = client.post("/api/round", json={"nick": "ada <b>"}).json()
    assert r["nick"] == "ADA B" and r["count"] == 6
    rid = r["round_id"]

    tiers = []
    for i in range(r["count"]):
        s = client.get(f"/api/round/{rid}/{i}").json()
        assert set(s) == {"idx", "label", "n", "values"}     # nothing that leaks the answer
        mid = s["n"] // 2
        rev = client.post(f"/api/round/{rid}/{i}/submit",
                          json={"ranges": [[mid - 20, mid + 20]], "nothing": False,
                                "elapsed_ms": 1234, "view": {"zooms": 2}}).json()
        tiers.append(rev["tier"])
        assert all(len(d["score"]) == s["n"] for d in rev["detectors"])
        assert len(rev["team_score"]) == s["n"]
        assert rev["you"]["points"] == rev["you"]["hits"] - rev["you"]["false_alarms"] + rev["you"]["clean"]
        assert client.post(f"/api/round/{rid}/{i}/feedback", json={"answer": "see"}).json()["ok"]

    assert sorted(tiers) == sorted(["easy", "easy", "medium", "medium", "unsolved", "decoy"])
    fin = client.post(f"/api/round/{rid}/finish", json={}).json()
    assert len(fin["results"]) == 6 and fin["rank"] == 0
    assert fin["leaderboard"][0]["name"] == "ADA B"
    assert fin["stats"]["plays"] == 1 and fin["stats"]["det_avg"] == fin["det_total"]


def test_bad_requests(client):
    rid = client.post("/api/round", json={}).json()["round_id"]
    assert client.get("/api/round/nope/0").status_code == 404
    assert client.get(f"/api/round/{rid}/9").status_code == 404
    assert client.post(f"/api/round/{rid}/0/feedback", json={"answer": "maybe"}).status_code == 400
    assert client.post(f"/api/round/{rid}/0/submit", json={"ranges": "x"}).status_code == 400


def test_window_holds_only_the_first_anomaly():
    import random

    from build_pack import usable, window_around_first

    y = np.zeros(5000, dtype=int)
    y[1200:1230] = y[2000:2010] = y[2600:2610] = 1
    rng = random.Random(0)
    for _ in range(20):
        a, b = window_around_first(y, 4000, rng, max_labels=1)
        assert a <= 1200 and 1229 < b <= 2000
        assert labels_to_ranges(y[a:b]) == [[1200 - a, 1229 - a]]
    a, b = window_around_first(y, 4000, rng, max_labels=2)
    assert len(labels_to_ranges(y[a:b])) <= 2 and b <= 2600
    a, b = window_around_first(y, 4000, rng, max_labels=0)
    assert b - a == 4000 and a <= 1200 < b
    short = np.zeros(800, dtype=int)
    short[100:110] = 1
    assert window_around_first(short, 4000, rng) == (0, 800)

    assert usable(np.arange(100))
    assert not usable(np.ones(100))
    assert not usable([1.0, np.nan, 2.0])


def test_build_pack_on_a_tiny_benchmark(tmp_path):
    """build_pack.py end to end, on a fake benchmark in the common format."""
    pd = pytest.importorskip("pandas")
    import subprocess

    root = tmp_path / "bench" / "fakebench"
    dets = ["DetA", "DetB", "DetC"]
    rng = np.random.default_rng(0)
    rows = {d: [] for d in dets}
    for k in range(14):
        n = 3000 + 500 * k
        first = 1200 + 40 * k
        name = f"{k + 1:03d}_FAKE_id_{k + 1}_Sensor_tr_500_1st_{first}.csv"
        y = np.zeros(n, dtype=int)
        y[first:first + 30] = 1
        v = np.sin(np.arange(n) / 20) + rng.normal(0, 0.1, n)
        v[first:first + 30] += 2
        if k == 12:                 # three anomalies: the window must hold only the first
            y[first + 900:first + 930] = y[first + 1800:first + 1830] = 1
        if k == 13:                 # a flat line: never playable, the only "unsolved" candidate
            v = np.ones(n)
            flat = name
        (root / "raw" / "uni").mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"Data": v, "Label": y}).to_csv(root / "raw" / "uni" / name, index=False)
        for j, d in enumerate(dets):
            s = rng.random(n) * 0.2
            if j <= k % 3:          # how many detectors see it varies by series
                s[first:first + 30] += 1
            (root / "scores" / "uni" / d).mkdir(parents=True, exist_ok=True)
            np.save(root / "scores" / "uni" / d / name.replace(".csv", ".npy"), s)
            rows[d].append({"File Name": name, "Model Name": d,
                            "VUS-PR": 0.9 if (j <= k % 3 or k == 12) and k != 13 else 0.1})
    (root / "metrics" / "uni").mkdir(parents=True)
    for d in dets:
        pd.DataFrame(rows[d]).to_csv(root / "metrics" / "uni" / f"{d}.csv", index=False)

    out = tmp_path / "pack"
    env = {**__import__("os").environ, "TSAD_BENCHMARKS": str(tmp_path / "bench")}
    r = subprocess.run([sys.executable, str(GAME / "build_pack.py"), "--benchmark", "fakebench",
                        "--detectors", *dets, "--per-tier", "6", "--max-len", "4000", "--out", str(out)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr

    from pack import load_pack
    pack = load_pack(out)
    tiers = [s.tier for s in pack.series.values()]
    # 9 easy candidates (two or three detectors solve them), 4 medium, the flat
    # one unsolved; the decoys come from what is left, the flat one included.
    assert sorted(tiers) == ["decoy"] * 3 + ["easy"] * 6 + ["medium"] * 4, tiers
    assert all(s.source["filename"] != flat for s in pack.series.values())
    for s in pack.series.values():
        assert 1000 <= s.n <= 4000
        if s.tier == "decoy":
            assert s.labels == []
        else:
            assert len(s.labels) == 1 and s.labels[0][1] - s.labels[0][0] == 29
            assert s.source["filename"].endswith(".csv")
    assert "unsolved flat x1" in r.stdout and "decoy flat x1" in r.stdout, r.stdout
