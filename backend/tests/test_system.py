import subprocess
from importlib import metadata

import pytest
from fastapi.testclient import TestClient

from app.api import system
from app.main import create_app


def test_missing_binary(monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda _: None)
    result = system.check_binary("ffmpeg", "-version", 6)
    assert result.status == "missing"
    assert result.version is None


@pytest.mark.parametrize("version,status", [("5.1.6", "outdated"), ("6.0", "ready"), ("8.1.3", "ready"), ("N-12345-gabc", "ready")])
def test_ffmpeg_versions(monkeypatch, version, status):
    monkeypatch.setattr(system.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(system.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, f"ffmpeg version {version} Copyright\n", ""))
    result = system.check_binary("ffmpeg", "-version", 6)
    assert (result.version, result.status) == (version, status)


def test_deno_multiline_version(monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda _: "/usr/bin/deno")
    monkeypatch.setattr(system.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "deno 2.5.0 (stable)\nv8 14.0\ntypescript 5.9\n", ""))
    assert system.check_binary("deno", "--version").version == "2.5.0"


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("ffmpeg", 5), PermissionError("blocked")])
def test_binary_failure_is_readable(monkeypatch, failure):
    monkeypatch.setattr(system.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(system.subprocess, "run", fail)
    result = system.check_binary("ffmpeg", "-version", 6)
    assert result.status == "error"
    assert result.message


def test_missing_python_ytdlp(monkeypatch):
    def missing(_):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(system.metadata, "version", missing)
    assert system.check_ytdlp().status == "missing"


@pytest.mark.parametrize("version,expected_option", [("6.1", "-filter_complex_script"), ("7.0", "-/filter_complex"), ("8.1.3", "-/filter_complex")])
def test_api_ready_and_ffmpeg_graph_option(monkeypatch, tmp_path, version, expected_option):
    monkeypatch.setattr(system, "check_binary", lambda name, *args: system.ToolCheck(id=name, version=version, status="ready"))
    monkeypatch.setattr(system, "check_ytdlp", lambda: system.ToolCheck(id="yt-dlp", version="2026.10.26", status="ready"))
    response = TestClient(create_app(tmp_path)).get("/api/system/check")
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["filter_graph_option"] == expected_option
    assert len(response.json()["tools"]) == 4


def test_missing_tools_do_not_crash_api(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "check_binary", lambda name, *args: system.ToolCheck(id=name, status="missing"))
    monkeypatch.setattr(system, "check_ytdlp", lambda: system.ToolCheck(id="yt-dlp", status="missing"))
    response = TestClient(create_app(tmp_path)).get("/api/system/check")
    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["filter_graph_option"] is None


def test_frontend_build_and_api_are_served_together(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Wedding Mix Maker</title>")
    client = TestClient(create_app(tmp_path))
    assert "Wedding Mix Maker" in client.get("/").text
    assert client.get("/api/not-a-route").status_code == 404
    assert client.get("/api/not-a-route").json() == {"detail": "API endpoint not found"}


def test_unbuilt_frontend_has_actionable_message(tmp_path):
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 503
    assert "make run" in response.json()["message"]
