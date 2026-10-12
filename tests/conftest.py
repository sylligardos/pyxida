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

# Absolute path to the data root. Edit this if you move the data directory.
DATA_PATH = REPO_ROOT / "data"


@pytest.fixture(scope="session")
def parser_uni():
    return TSBADParser(DATA_PATH, kind="uni")


@pytest.fixture(scope="session")
def parser_multi():
    return TSBADParser(DATA_PATH, kind="multi")
