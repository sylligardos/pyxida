"""Shared pytest fixtures for TSBADParser tests."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Non-interactive backend before anything imports pyplot: the visualize tests
# call plt.show(), which otherwise opens a window per test and blocks the run
# until someone closes it.
import matplotlib
matplotlib.use("Agg")

import pytest
from app.parser import TSBADParser  # noqa: E402

# TSB-AD itself (raw series, scores, metrics), where the parser looks for it:
# $TSAD_BENCHMARKS/tsb-ad, else the repo's data/ links. The parser tests need
# it and are skipped without it (a fresh clone has only data/splits).
DATA_PATH = TSBADParser.benchmarks_root() / "tsb-ad"
if not (DATA_PATH / "raw").exists():
    DATA_PATH = REPO_ROOT / "data"
HAS_TSB_AD = (DATA_PATH / "raw" / "uni").exists()


@pytest.fixture(scope="session")
def parser_uni():
    return TSBADParser(DATA_PATH, kind="uni")


@pytest.fixture(scope="session")
def parser_multi():
    return TSBADParser(DATA_PATH, kind="multi")
