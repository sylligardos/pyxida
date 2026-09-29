"""Shared pytest fixtures for TSBADParser tests."""

from pathlib import Path

# Non-interactive backend before anything imports pyplot: the visualize tests
# call plt.show(), which otherwise opens a window per test and blocks the run
# until someone closes it.
import matplotlib
matplotlib.use("Agg")

import pytest
from tsbadparser import TSBADParser

# Absolute path to the data root. Edit this if you move the data directory.
DATA_PATH = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="session")
def parser_uni():
    return TSBADParser(DATA_PATH, kind="uni")


@pytest.fixture(scope="session")
def parser_multi():
    return TSBADParser(DATA_PATH, kind="multi")
