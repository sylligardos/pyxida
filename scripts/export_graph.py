"""
@who: Emmanouil Sylligardos (Sylli)
@where: Paris
@when: 2026 (3rd year PhD)
@what: The series graph for the web demo: every series a node, the edge
       between two series the covariance of their detector-score profiles
       (the sum over detector pairs of the score gap on one series times the
       gap on the other). Only the K strongest positive edges of each node
       are kept and drawn; positions come from a force layout. Louvain
       communities of that graph are the "neighbourhoods" the page lists.

Reads data/web/<benchmark>/<kind>/landscape.json (export_web.py writes it)
and writes graph.json next to it, one graph per scope (whole benchmark, each
dataset, each entity type) and per metric.

Run, from the repo root:
    python scripts/export_graph.py --benchmark tsb-ad --kind uni
"""

import argparse
import json
from pathlib import Path

import networkx as nx
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "data" / "web"

K = 10            # edges kept per node
MIN_SERIES = 3    # a scope with fewer series gets no graph
METRICS = ("aucpr", "vus")


def build(rows: list[dict], metric: str) -> dict:
    """Nodes, edges and positions of one scope for one metric. A series with
    no score at all is dropped; a detector missing on any kept series is
    dropped so every profile has the same detectors."""
    S = np.array([[np.nan if v is None else v for v in r[metric]] for r in rows], dtype=float)
    keep_series = ~np.isnan(S).all(axis=1)
    S = S[keep_series]
    keep_det = ~np.isnan(S).any(axis=0)
    S = S[:, keep_det]
    files = [r["file"] for r, ok in zip(rows, keep_series) if ok]
    if len(files) < MIN_SERIES or S.shape[1] < 2:
        return {"nodes": [], "edges": [], "community": [], "dropped_series": [r["file"] for r, ok in zip(rows, keep_series) if not ok], "dropped_detectors": []}

    S = S - S.mean(axis=1, keepdims=True)
    W = S @ S.T / S.shape[1]
    np.fill_diagonal(W, -np.inf)

    G = nx.Graph()
    G.add_nodes_from(range(len(files)))
    for i in range(len(files)):
        for j in np.argsort(W[i])[::-1][:K]:
            if W[i, j] > 0:
                G.add_edge(i, int(j), weight=float(W[i, j]))
    pos = nx.spring_layout(G, weight="weight", seed=0)

    # Communities numbered by size, largest first; the ones too small to
    # show are merged into one "other" community, listed last.
    comms = sorted(nx.community.louvain_communities(G, weight="weight", seed=0), key=len, reverse=True)
    big = [c for c in comms if len(c) >= MIN_SERIES]
    small = [n for c in comms if len(c) < MIN_SERIES for n in c]
    community = [0] * len(files)
    for label, members in enumerate(big + ([set(small)] if small else [])):
        for n in members:
            community[n] = label

    return {
        "files": files,
        "nodes": [[round(float(pos[i][0]), 4), round(float(pos[i][1]), 4)] for i in range(len(files))],
        "edges": [[i, j, round(w, 5)] for i, j, w in G.edges(data="weight")],
        "community": community,
        "n_small_merged": len(small),
        "n_detectors": int(S.shape[1]),
        "dropped_series": [r["file"] for r, ok in zip(rows, keep_series) if not ok],
        "dropped_detectors": [],  # filled by the caller, it knows the names
        "_keep_det": keep_det,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--kind", default="uni", choices=["uni", "multi"])
    a = ap.parse_args()

    folder = WEB / a.benchmark / a.kind
    land = json.loads((folder / "landscape.json").read_text())
    detectors, rows = land["detectors"], land["rows"]

    scopes = [("all", "")]
    scopes += [("dataset", d) for d in sorted({r["dataset"] for r in rows})]
    scopes += [("type", t) for t in sorted({r["type"] for r in rows})]

    # Mean anomaly length of every series, from the exported label runs
    # (series/<stem>.json); missing when the series is not exported.
    anomaly_len = {}
    for r in rows:
        f = folder / "series" / (r["file"][:-4] + ".json")
        if f.exists():
            runs = json.loads(f.read_text()).get("labels", [])
            anomaly_len[r["file"]] = round(sum(b - a + 1 for a, b in runs) / len(runs), 1) if runs else None
    print(f"anomaly length known for {len(anomaly_len)} of {len(rows)} series")

    out = {"k": K, "metrics": land["metrics"], "anomaly_len": anomaly_len, "scopes": [], "graphs": {}}
    for group, value in scopes:
        sub = [r for r in rows if group == "all" or r[group] == value]
        if len(sub) < MIN_SERIES:
            continue
        key = group if group == "all" else f"{group}:{value}"
        out["scopes"].append({"key": key, "group": group, "value": value, "n": len(sub)})
        out["graphs"][key] = {}
        for metric in METRICS:
            g = build(sub, metric)
            keep = g.pop("_keep_det", None)
            if keep is not None:
                g["dropped_detectors"] = [d for d, ok in zip(detectors, keep) if not ok]
            out["graphs"][key][metric] = g
            n_comm = len(set(g["community"]))
            print(f"{key:28s} {metric:5s} series {len(g.get('files', [])):4d}  communities {n_comm:2d}  "
                  f"dropped series {len(g['dropped_series']):3d}  dropped detectors {len(g['dropped_detectors']):2d} {g['dropped_detectors']}")

    (folder / "graph.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {folder / 'graph.json'}")


if __name__ == "__main__":
    main()
