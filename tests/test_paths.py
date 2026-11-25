from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from utils.paths import get_resource_path

REPO_ROOT = SRC_ROOT.parent


def test_resource_path_from_source_points_at_repo_assets():
    path = get_resource_path("assets/icon.ico")
    assert path == REPO_ROOT / "assets" / "icon.ico"
    assert path.exists()


def test_resource_path_in_frozen_build_uses_meipass(tmp_path):
    with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
        assert get_resource_path("assets/icon.ico") == tmp_path / "assets" / "icon.ico"
