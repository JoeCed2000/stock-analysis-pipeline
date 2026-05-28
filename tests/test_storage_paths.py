from pathlib import Path

import pytest

from backend.earnings_deep_dive.schemas import DeepDiveRequest
import backend.storage_paths as storage_paths


def test_get_analyses_dir_defaults_to_repo_root(monkeypatch):
    monkeypatch.delenv(storage_paths.ANALYSES_DIR_ENV_VAR, raising=False)
    monkeypatch.setattr(storage_paths, "_read_dotenv_value", lambda key: None)

    assert storage_paths.get_analyses_dir(create=False) == storage_paths.DEFAULT_ANALYSES_DIR


def test_get_analyses_dir_uses_env_override(monkeypatch, tmp_path):
    shared_root = tmp_path / "shared-analyses"
    monkeypatch.setenv(storage_paths.ANALYSES_DIR_ENV_VAR, str(shared_root))

    resolved = storage_paths.get_analyses_dir(create=False)

    assert resolved == shared_root.resolve()


def test_deep_dive_request_accepts_output_dir_under_shared_root(monkeypatch, tmp_path):
    shared_root = tmp_path / "shared-analyses"
    output_dir = shared_root / "2026-05-28_AAPL_Apple_Inc"
    output_dir.mkdir(parents=True)
    monkeypatch.setenv(storage_paths.ANALYSES_DIR_ENV_VAR, str(shared_root))

    req = DeepDiveRequest(ticker="AAPL", output_dir=str(output_dir))

    assert req.output_dir == str(output_dir)


def test_deep_dive_request_rejects_output_dir_outside_shared_root(monkeypatch, tmp_path):
    shared_root = tmp_path / "shared-analyses"
    shared_root.mkdir(parents=True)
    outside_dir = tmp_path / "outside" / "2026-05-28_AAPL_Apple_Inc"
    outside_dir.mkdir(parents=True)
    monkeypatch.setenv(storage_paths.ANALYSES_DIR_ENV_VAR, str(shared_root))

    with pytest.raises(ValueError, match="output_dir must be under"):
        DeepDiveRequest(ticker="AAPL", output_dir=str(outside_dir))
