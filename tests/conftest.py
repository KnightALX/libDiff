import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures_dir():
    return FIXTURES


@pytest.fixture
def example_lib(fixtures_dir):
    return str(fixtures_dir / "example.lib")


@pytest.fixture
def stdcell_base(fixtures_dir):
    return str(fixtures_dir / "stdcell_base.lib")


@pytest.fixture
def stdcell_perturbed(fixtures_dir):
    return str(fixtures_dir / "stdcell_perturbed.lib")
