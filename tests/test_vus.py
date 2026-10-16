"""VUS-PR: scripts/vus.py must give what TSB-AD's own code gives.

The expected values come from TSB-AD (commit 6beac72),
TSB_AD.evaluation.basic_metrics.generate_curve(label, score, L)[-1],
on the synthetic series below.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from vus import vus_pr  # noqa: E402

TSB_AD = {0: 0.10238203615387782, 4: 0.1192322897808733, 16: 0.21618342096448037, 64: 0.3434428313406758}


def synthetic():
    rng = np.random.default_rng(0)
    n = 2000
    label = np.zeros(n, int)
    label[300:320] = 1
    label[1200:1201] = 1
    label[1700:1760] = 1
    score = rng.random(n) * 0.5
    score[305:325] += 0.6
    score[1195:1199] += 0.4
    score[1650:1700] += 0.3
    return label, score


def test_matches_tsb_ad():
    label, score = synthetic()
    got = vus_pr(label, score, list(TSB_AD))
    for L, want in TSB_AD.items():
        assert got[L] == pytest.approx(want, abs=1e-12), L


def test_grows_with_the_buffer_on_a_late_detector():
    label, score = synthetic()
    got = vus_pr(label, score, [0, 16, 64])
    assert got[0] < got[16] < got[64]
