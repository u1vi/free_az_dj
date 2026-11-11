"""YouTube logic is deterministic offline; real downloading is explicitly opt-in."""

import errno
import io
import math
import os
import threading
import time
import wave
from array import array
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.youtube import router
from app.audio.ffprobe import AudioError
from app.database import Database
from app.importers import youtube
from app.jobs import JobRunner
from app.models import Job, Track

FIRST = "abcdefghijk"
SECOND = "lmnopqrstuv"
THIRD = "wxyz0123456"
PLAYLIST = "PLabcdefghijklmnopqrstuvwx"


@pytest.fixture
def database(tmp_path):
    result = Database(tmp_path / "data")
    yield result
    result.engine.dispose()


def add_track(database, title="YouTube video"):
    track = Track(title=title, source_type="youtube", source_url=f"https://www.youtube.com/watch?v={FIRST}", original_name="YouTube video", original_suffix=".pending")
    job = Job(track_id=track.id, kind="import_youtube")
    track.job_id = job.id
    with Session(database.engine, expire_on_commit=False) as session:
        session.add(track)
        session.add(job)
        session.commit()
    return track, job


@pytest.fixture
def application(database, monkeypatch):
    runner = JobRunner(database)
    submitted = []
    monkeypatch.setattr(runner, "submit", submitted.append)
    app = FastAPI()
    app.state.database, app.state.jobs = database, runner
    app.include_router(router)
    with TestClient(app) as client:
        yield client, database, submitted
    runner.close()


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={FIRST}&si=tracking&t=10&list={PLAYLIST}",
    f"https://youtube.com/watch?v={FIRST}",
    f"https://youtu.be/{FIRST}?si=tracking",
    f"https://music.youtube.com/watch?v={FIRST}&feature=share",
    f"https://youtube.com/shorts/{FIRST}?feature=share",
    f"http://m.youtube.com/watch?v={FIRST}",
])
def test_video_urls_are_canonical_single_videos(url):
    parsed = youtube.parse_url(url)
    assert parsed.url == f"https://www.youtube.com/watch?v={FIRST}"
    assert parsed.video_id == FIRST
    assert not parsed.is_playlist


@pytest.mark.parametrize("url", [
    f"https://youtube.com/playlist?list={PLAYLIST}&si=tracking",
    f"https://music.youtube.com/playlist?list={PLAYLIST}",
    f"https://youtube.com/watch?list={PLAYLIST}",
])
def test_playlist_urls_are_canonical(url):
    assert youtube.parse_url(url).url == f"https://www.youtube.com/playlist?list={PLAYLIST}"
    assert youtube.parse_url(url).is_playlist


@pytest.mark.parametrize("url", [
    "file:///tmp/song.wav", "https://example.com/watch?v=abcdefghijk",
    "https://youtube.com.evil.test/watch?v=abcdefghijk", "https://youtube.com@evil.test/watch?v=abcdefghijk",
    "https://user:password@youtube.com/watch?v=abcdefghijk", "https://youtube.com:8080/watch?v=abcdefghijk",
    "https://youtu.be/../../abcdefghijk", "https://youtube.com/watch?v=too-short",
    "https://youtube.com/redirect?q=https://evil.test", "https://youtube.com/playlist?list=bad",
    "https://youtube.com/shorts/abcdefghijk/extra", "https://youtube.com/watch?v=abcdefghijk%26x=bad",
])
def test_untrusted_and_invalid_urls_are_rejected(url):
    with pytest.raises(AudioError, match="valid YouTube"):
        youtube.parse_url(url)


@pytest.mark.parametrize("error,fragment", [
    ("ERROR: Private video. Sign in", "unavailable or private"),
    ("Video unavailable", "unavailable or private"),
    ("This video is not available", "unavailable or private"),
    ("This video is not available in your country", "blocked in your region"),
    ("The uploader has not made this video available in your country", "blocked in your region"),
    ("Sign in to confirm your age", "age-restricted"),
    ("Sign in to confirm you're not a bot", "browser sign-in"),
    ("Temporary failure in name resolution", "internet connection"),
    (TimeoutError("download stalled"), "internet connection"),
    ("Signature extraction failed", "python -m pip install -U 'yt-dlp[default]'"),
    ("HTTP Error 429: Too many requests", "limiting downloads"),
    ("No supported JavaScript runtime could be found", "Deno is missing"),
])
def test_plain_error_messages(error, fragment):
    assert fragment in youtube.error_message(error)


def downloader_factory(monkeypatch, *, entries=None, payload=b"downloaded bytes", duration=180, title="Toy ə ğ ş — ж", failure=None, during_download=None, extension="webm"):
    settings = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            settings.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            if failure:
                raise failure
            if not download:
                return {"entries": entries}
            if during_download:
                during_download()
            path = Path(self.options["outtmpl"] % {"ext": extension})
            for hook in self.options.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": len(payload), "total_bytes": len(payload)})
            path.write_bytes(payload)
            for hook in self.options.get("progress_hooks", []):
                hook({"status": "finished", "filename": str(path)})
            return {"title": title, "duration": duration, "ext": extension, "requested_downloads": [{"filepath": str(path)}]}

        def prepare_filename(self, info):
            return self.options.get("outtmpl", "") % {"ext": info.get("ext", "webm")}

    monkeypatch.setattr(youtube, "YoutubeDL", FakeDownloader)
    return settings


def test_three_video_playlist_returns_metadata_without_downloading(application, monkeypatch):
    client, database, submitted = application
    settings = downloader_factory(monkeypatch, entries=[
        {"id": FIRST, "title": "First ə", "duration": 120},
        {"id": SECOND, "title": "Second ж", "duration": 1500},
        {"url": f"https://youtu.be/{THIRD}", "title": "Third", "duration": None},
        None, {"id": FIRST, "title": "Duplicate"}, {"id": "invalid"},
    ])
    result = client.post("/api/tracks/youtube", json={"url": f"https://youtube.com/playlist?list={PLAYLIST}"})
    assert result.status_code == 200
    body = result.json()
    assert body["jobs"] == []
    assert [entry["title"] for entry in body["playlist"]] == ["First ə", "Second ж", "Third"]
    assert body["playlist"][2]["duration_s"] is None
    assert "20 minutes" in body["warning"]
    assert submitted == []
    assert settings[0]["extract_flat"] == "in_playlist"
    assert settings[0]["noplaylist"] is False
    with Session(database.engine) as session:
        assert session.exec(select(Track)).all() == []


def test_selected_playlist_videos_each_become_a_job(application):
    client, database, submitted = application
    urls = [f"https://youtu.be/{identifier}" for identifier in (FIRST, SECOND, THIRD, FIRST)]
    response = client.post("/api/tracks/youtube", json={"url": f"https://youtube.com/playlist?list={PLAYLIST}", "playlist": urls})
    assert response.status_code == 202
    assert len(response.json()["jobs"]) == 3
    assert len(submitted) == 3
    with Session(database.engine) as session:
        tracks = session.exec(select(Track)).all()
        assert len(tracks) == 3
        assert all(track.status == "importing" and track.source_type == "youtube" for track in tracks)
        assert all(track.original_suffix == ".pending" for track in tracks)


@pytest.mark.parametrize("url", [f"https://youtube.com/watch?v={FIRST}", f"https://youtu.be/{FIRST}"])
def test_single_video_queues_without_metadata_network_call(application, monkeypatch, url):
    client, database, submitted = application
    monkeypatch.setattr(youtube, "YoutubeDL", lambda _: pytest.fail("Single-video request must queue without network access"))
    response = client.post("/api/tracks/youtube", json={"url": url})
    assert response.status_code == 202
    assert response.json()["jobs"][0]["kind"] == "import_youtube"
    assert len(submitted) == 1
    with Session(database.engine) as session:
        track = session.exec(select(Track)).one()
        assert track.source_url == f"https://www.youtube.com/watch?v={FIRST}"


def test_invalid_requests_and_private_playlist_are_readable(application, monkeypatch):
    client, _, submitted = application
    assert client.post("/api/tracks/youtube", json={"url": "https://evil.test"}).status_code == 400
    assert client.post("/api/tracks/youtube", json={"url": f"https://youtube.com/playlist?list={PLAYLIST}", "playlist": []}).status_code == 400
    downloader_factory(monkeypatch, failure=RuntimeError("Private video"))
    response = client.post("/api/tracks/youtube", json={"url": f"https://youtube.com/playlist?list={PLAYLIST}"})
    assert response.status_code == 400
    assert "private" in response.json()["detail"]
    assert submitted == []


def test_download_persists_safe_original_and_title(database, monkeypatch):
    track, job = add_track(database)
    settings = downloader_factory(monkeypatch)
    progress = []
    youtube.download_original(database, track, lambda value, message: progress.append((value, message)))
    with Session(database.engine) as session:
        current = session.get(Track, track.id)
        assert current.title == "Toy ə ğ ş — ж"
        assert current.original_suffix == ".webm"
        assert current.original_name == "Toy ə ğ ş — ж.webm"
        assert database.original(current).name == f"{track.id}.webm"
        assert database.original(current).read_bytes() == b"downloaded bytes"
    assert settings[0]["format"] == "bestaudio/best"
    assert settings[0]["noplaylist"] is True
    assert settings[0]["js_runtimes"] == {"deno": {}}
    assert all(0 <= value <= 0.08 for value, _ in progress)
    assert any(message == "Downloading audio" for _, message in progress)


def test_user_rename_is_not_overwritten_and_long_video_warns(database, monkeypatch):
    track, job = add_track(database)
    downloader_factory(monkeypatch, duration=1300)
    with Session(database.engine) as session:
        current = session.get(Track, track.id)
        current.title = "My wedding song"
        session.add(current)
        session.commit()
    youtube.download_original(database, track, lambda *args: None)
    with Session(database.engine) as session:
        assert session.get(Track, track.id).title == "My wedding song"
        assert "20 minutes" in session.get(Job, job.id).result_json["warning"]


def test_failed_download_uses_plain_error_and_preserves_disk_error(database, monkeypatch):
    track, _ = add_track(database)
    downloader_factory(monkeypatch, failure=RuntimeError("Private video"))
    with pytest.raises(AudioError, match="private"):
        youtube.download_original(database, track, lambda *args: None)
    downloader_factory(monkeypatch, failure=ConnectionError("connection failed"))
    with pytest.raises(AudioError, match="internet connection"):
        youtube.download_original(database, track, lambda *args: None)
    downloader_factory(monkeypatch, failure=OSError(errno.ENOSPC, "No space left on device"))
    with pytest.raises(OSError) as failure:
        youtube.download_original(database, track, lambda *args: None)
    assert failure.value.errno == errno.ENOSPC


def test_downloads_are_limited_to_two_at_once(database, monkeypatch):
    active = 0
    maximum = 0
    lock = threading.Lock()

    def during_download():
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.04)
        with lock:
            active -= 1

    downloader_factory(monkeypatch, during_download=during_download)
    tracks = [add_track(database)[0] for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda track: youtube.download_original(database, track, lambda *args: None), tracks))
    assert maximum == 2


def tone_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(array("h", (round(math.sin(index * 2 * math.pi * 440 / 44100) * 8000) for index in range(44100))).tobytes())
    return buffer.getvalue()


def wait_job(database, identifier):
    for _ in range(200):
        with Session(database.engine) as session:
            job = session.get(Job, identifier)
            if job.status in ("done", "error"):
                session.expunge(job)
                return job
        time.sleep(0.05)
    pytest.fail("YouTube job did not finish")


def test_youtube_runner_reloads_original_then_runs_shared_pipeline(database, monkeypatch):
    downloader_factory(monkeypatch, payload=tone_wav(), extension="wav", duration=1300)
    runner = JobRunner(database)
    track, job = add_track(database)
    try:
        runner.submit(job.id)
        done = wait_job(database, job.id)
        assert done.status == "done", done.message
        assert done.progress == 1
        assert done.result_json["track_id"] == track.id
        assert "20 minutes" in done.result_json["warning"]
        with Session(database.engine) as session:
            current = session.get(Track, track.id)
            assert current.status == "ready"
            assert current.title == "Toy ə ğ ş — ж"
            assert current.duration_s == pytest.approx(1, abs=0.01)
            assert database.original(current).suffix == ".wav"
            assert database.working(track.id).is_file()
            assert database.peaks(track.id).is_file()
    finally:
        runner.close()


def test_private_job_is_retryable_without_original_and_runner_keeps_working(database, monkeypatch):
    from app.api.jobs import router as jobs_router
    from app.api.tracks import router as tracks_router

    downloader_factory(monkeypatch, failure=RuntimeError("Private video"))
    runner = JobRunner(database)
    app = FastAPI()
    app.state.database, app.state.jobs = database, runner
    app.include_router(router)
    app.include_router(tracks_router)
    app.include_router(jobs_router)
    try:
        with TestClient(app) as client:
            response = client.post("/api/tracks/youtube", json={"url": f"https://youtu.be/{FIRST}"})
            assert response.status_code == 202
            failed = wait_job(database, response.json()["jobs"][0]["id"])
            assert failed.status == "error"
            assert "private" in failed.message
            track = client.get("/api/tracks").json()[0]
            assert track["can_retry"] is True
            with Session(database.engine) as session:
                assert not database.original(session.get(Track, track["id"])).is_file()

            downloader_factory(monkeypatch, payload=tone_wav(), extension="wav")
            retry = client.post(f"/api/tracks/{track['id']}/retry")
            assert retry.status_code == 202
            assert retry.json()["kind"] == "import_youtube"
            assert wait_job(database, retry.json()["id"]).status == "done"
            assert client.get("/api/tracks").json()[0]["status"] == "ready"
    finally:
        runner.close()


@pytest.mark.parametrize("renamed", [False, True])
def test_embedded_audio_tags_do_not_override_youtube_or_user_title(database, monkeypatch, renamed):
    from app import jobs as jobs_module

    runner = JobRunner(database)
    track, job = add_track(database)

    def during_download():
        if renamed:
            with Session(database.engine) as session:
                current = session.get(Track, track.id)
                current.title = "My chosen wedding title"
                session.add(current)
                session.commit()

    downloader_factory(monkeypatch, during_download=during_download)
    monkeypatch.setattr(jobs_module, "import_original", lambda *args: {"duration_s": 1, "tag_title": "Wrong embedded title"})
    try:
        runner.run_import(job.id)
        with Session(database.engine) as session:
            assert session.get(Job, job.id).status == "done"
            expected = "My chosen wedding title" if renamed else "Toy ə ğ ş — ж"
            assert session.get(Track, track.id).title == expected
    finally:
        runner.close()


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("WEDDING_MIX_YOUTUBE_NETWORK_URL"), reason="Set WEDDING_MIX_YOUTUBE_NETWORK_URL to opt into a real download")
def test_real_youtube_download(database):
    parsed = youtube.parse_url(os.environ["WEDDING_MIX_YOUTUBE_NETWORK_URL"])
    track, _ = add_track(database)
    with Session(database.engine) as session:
        current = session.get(Track, track.id)
        current.source_url = parsed.url
        session.add(current)
        session.commit()
    track.source_url = parsed.url
    youtube.download_original(database, track, lambda *args: None)
    with Session(database.engine) as session:
        assert database.original(session.get(Track, track.id)).stat().st_size > 0
