import os
from pathlib import Path
import sys
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from path_utils import get_validated_file_path, DATA_FILES_DIR


def test_get_validated_file_path_valid(tmp_path):
    sample = DATA_FILES_DIR / "sample.txt"
    sample.write_text("data")
    result = get_validated_file_path("sample.txt")
    assert result == sample


def test_get_validated_file_path_malicious():
    with pytest.raises(ValueError):
        get_validated_file_path("../main.py")


def test_get_validated_file_path_not_found():
    with pytest.raises(FileNotFoundError):
        get_validated_file_path("missing.txt")
