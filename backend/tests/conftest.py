from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT_DIR, Settings
from app.db import SqliteRepository
from app.factory import create_app
from app.schemes import load_schemes, review_scheme


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Replay mode, SQLite and a private copy of knowledge/ in a temp dir, and no .env file, so a developer's
    real keys never leak in and a test that reviews a scheme never edits the repository's YAML."""
    knowledge = tmp_path / "knowledge"
    shutil.copytree(ROOT_DIR / "knowledge", knowledge)
    return Settings(
        _env_file=None,
        tinyfish_mode="replay",
        db_backend="sqlite",
        sqlite_path=tmp_path / "test.db",
        files_dir=tmp_path / "files",
        cache_dir=tmp_path / "cache",
        knowledge_dir=knowledge,
        demo_state="Uttar Pradesh",
        demo_district="Meerut",
    )


def review_all(settings: Settings, reviewer: str = "Test Reviewer") -> None:
    for scheme in load_schemes(settings):
        review_scheme(settings, scheme.id, reviewer)


@pytest.fixture
def repo(settings) -> SqliteRepository:
    return SqliteRepository(settings.sqlite_path)


@pytest.fixture
def client(settings) -> TestClient:
    """Schemes are NOT reviewed here, exactly as shipped."""
    return TestClient(create_app(settings))


@pytest.fixture
def reviewed_client(settings) -> TestClient:
    review_all(settings)
    return TestClient(create_app(settings))
