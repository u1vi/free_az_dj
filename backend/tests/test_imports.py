"""Exercise real file formats through the API; no music assets are checked in."""

import json
import math
import shutil
import subprocess
import time
import wave
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.audio.peaks import write_peaks
from app.main import create_app


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("These integration checks require ffmpeg and ffprobe.")
    directory = tmp_path_factory.mktemp("generated-audio")

    def generate(name, arguments):
        path = directory / name
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", *arguments, str(path)],
            check=True, capture_output=True, timeout=30,
        )
        return path

    tone = ["-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=2"]
    results = {
        "mp3": generate("tone.mp3", [*tone, "-metadata", "title=Toy ə ğ ş — ж", "-c:a", "libmp3lame"]),
        "m4a": generate("tone.m4a", [*tone, "-c:a", "aac"]),
        "flac": generate("tone.flac", [*tone, "-c:a", "flac"]),
        "wav": generate("mono.wav", [*tone, "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le"]),
        "ogg": generate("tone.ogg", [*tone, "-c:a", "libvorbis"]),
        "opus": generate("tone.opus", [*tone, "-c:a", "libopus"]),
        "mp4": generate("video.mp4", ["-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2", *tone, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "mpeg4", "-c:a", "aac"]),
        "video_only": generate("silent-video.mp4", ["-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2", "-an", "-c:v", "mpeg4"]),
        "silence": generate("silence.wav", ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=1", "-c:a", "pcm_s16le"]),
        "padded": generate("padded.wav", ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.6", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=2", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.8", "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]", "-map", "[out]", "-c:a", "pcm_s16le"]),
        "multiple": generate("two-streams.mkv", ["-f", "lavfi", "-i", "sine=frequency=300:sample_rate=44100:duration=2", "-f", "lavfi", "-i", "sine=frequency=1700:sample_rate=44100:duration=2", "-map", "0:a", "-map", "1:a", "-c:a", "pcm_s16le"]),
    }
    return results


@pytest.fixture
def application(tmp_path):
    app = create_app(static_dir=tmp_path / "static", data_dir=tmp_path / "data")
    with TestClient(app) as client:
        yield client, app, tmp_path / "data"


def upload(client, *sources):
    files = [("files", (name, source.read_bytes() if isinstance(source, Path) else source, "application/octet-stream")) for name, source in sources]
    response = client.post("/api/tracks/upload", files=files)
    assert response.status_code == 202, response.text
    return response.json()


def finished(client, count=1, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get("/api/tracks")
        assert response.status_code == 200, response.text
        tracks = response.json()
        if len(tracks) == count and all(track["status"] != "importing" for track in tracks):
            return tracks
        time.sleep(0.05)
    pytest.fail(f"Imports did not finish within {timeout}s: {tracks}")


def test_mixed_batch_imports_and_corrupt_file(application, media):
    client, app, directory = application
    names = ["Song ə ğ.mp3", "With spaces.m4a", "Танец.flac", "mono.wav", "Wedding video.mp4"]
    jobs = upload(client, *zip(names, [media[key] for key in ("mp3", "m4a", "flac", "wav", "mp4")]), ("damaged.mp3", b"this is not audio"))
    assert len(jobs) == 6
    tracks = finished(client, count=6)
    ready = [track for track in tracks if track["status"] == "ready"]
    assert len(ready) == 5, tracks
    assert next(track for track in ready if track["original_name"] == names[0])["title"] == "Toy ə ğ ş — ж"
    for track in ready:
        assert track["duration_s"] == pytest.approx(2, abs=0.05)
        assert math.isfinite(track["loudness_lufs"])
        assert math.isfinite(track["true_peak_db"])
        assert track["job"]["status"] == "done"
        assert track["job"]["progress"] == 1
        job = client.get(f"/api/jobs/{track['job']['id']}").json()
        assert job["result_json"] == {"track_id": track["id"]}
        with wave.open(str(directory / "work" / f"{track['id']}.wav"), "rb") as working:
            assert (working.getframerate(), working.getnchannels(), working.getsampwidth()) == (44100, 2, 2)
        peaks = client.get(f"/api/tracks/{track['id']}/peaks").json()
        assert peaks["duration"] == pytest.approx(track["duration_s"], abs=0.001)
        assert 65 <= len(peaks["peaks"]) <= 69
        assert all(0 <= peak <= 1 for peak in peaks["peaks"])
    damaged = next(track for track in tracks if track["status"] == "error")
    assert "could not be read" in damaged["error"]
    assert damaged["can_retry"] is True
    assert damaged["job"]["status"] == "error"
    assert client.get(f"/api/tracks/{damaged['id']}/audio").status_code == 409
    assert all(0 <= job["progress"] <= 1 for job in jobs)


@pytest.mark.parametrize("kind", ["ogg", "opus"])
def test_additional_audio_formats(application, media, kind):
    client, _, _ = application
    upload(client, (f"song.{kind}", media[kind]))
    track = finished(client)[0]
    assert track["status"] == "ready", track
    assert track["duration_s"] == pytest.approx(2, abs=0.05)


def test_video_without_audio_is_clear_error_and_keeps_original(application, media):
    client, _, directory = application
    upload(client, ("video.mp4", media["video_only"]))
    track = finished(client)[0]
    assert track["status"] == "error"
    assert track["error"] == "This file has no audio."
    assert (directory / "originals" / f"{track['id']}.mp4").read_bytes() == media["video_only"].read_bytes()


def test_first_audio_stream_is_used(application, media):
    client, _, directory = application
    upload(client, ("two streams.mkv", media["multiple"]))
    track = finished(client)[0]
    assert track["status"] == "ready", track
    with wave.open(str(directory / "work" / f"{track['id']}.wav"), "rb") as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").reshape(-1, 2)[:, 0]
    frequency = np.fft.rfftfreq(len(samples), d=1 / 44100)[np.argmax(np.abs(np.fft.rfft(samples)))]
    assert frequency == pytest.approx(300, abs=1)


def test_silence_has_json_safe_loudness_and_full_trim(application, media):
    client, _, _ = application
    upload(client, ("silence.wav", media["silence"]))
    track = finished(client)[0]
    assert track["status"] == "ready", track
    assert track["loudness_lufs"] is None
    assert track["true_peak_db"] is None
    assert track["suggested_start_s"] == 0
    assert track["suggested_end_s"] == pytest.approx(1, abs=0.001)
    assert set(client.get(f"/api/tracks/{track['id']}/peaks").json()["peaks"]) == {0}
    json.dumps(track, allow_nan=False)


def test_leading_and_trailing_silence_are_suggestions_only(application, media):
    client, _, _ = application
    upload(client, ("padded.wav", media["padded"]))
    track = finished(client)[0]
    assert track["status"] == "ready", track
    assert track["duration_s"] == pytest.approx(3.4, abs=0.01)
    assert track["suggested_start_s"] == pytest.approx(0.6, abs=0.05)
    assert track["suggested_end_s"] == pytest.approx(2.6, abs=0.05)


def test_peak_math_includes_negative_full_scale_and_partial_bucket(tmp_path):
    source = tmp_path / "extremes.wav"
    samples = np.zeros((4410, 2), dtype="<i2")
    samples[0] = (32767, -32768)
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(samples.tobytes())
    destination = tmp_path / "peaks.json"
    write_peaks(source, destination)
    result = json.loads(destination.read_text())
    assert result["duration"] == 0.1
    assert result["peaks"] == [1, 0, 0, 0]


def test_working_audio_supports_http_ranges(application, media):
    client, _, _ = application
    upload(client, ("song.wav", media["wav"]))
    track = finished(client)[0]
    url = f"/api/tracks/{track['id']}/audio"
    full = client.get(url)
    assert full.status_code == 200
    partial = client.get(url, headers={"Range": "bytes=100-199"})
    assert partial.status_code == 206
    assert partial.content == full.content[100:200]
    assert partial.headers["content-range"] == f"bytes 100-199/{len(full.content)}"
    assert client.get(url, headers={"Range": f"bytes={len(full.content) + 100}-"}).status_code == 416


def test_file_names_are_display_only_and_rename_survives_restart(tmp_path, media):
    directory = tmp_path / "data"
    with TestClient(create_app(data_dir=directory, static_dir=tmp_path / "static")) as client:
        upload(client, ("../../Toy ə ş ж.wav", media["wav"]))
        track = finished(client)[0]
        UUID(track["id"])
        assert track["original_name"] == "Toy ə ş ж.wav"
        originals = list((directory / "originals").iterdir())
        assert [path.name for path in originals] == [f"{track['id']}.wav"]
        assert originals[0].read_bytes() == media["wav"].read_bytes()
        response = client.patch(f"/api/tracks/{track['id']}", json={"title": "  Gəlin — ж  "})
        assert response.status_code == 200
        assert response.json()["title"] == "Gəlin — ж"
        assert client.patch(f"/api/tracks/{track['id']}", json={"title": "   "}).status_code == 422
        assert client.patch(f"/api/tracks/{track['id']}", json={"title": "a" * 301}).status_code == 422
    with TestClient(create_app(data_dir=directory, static_dir=tmp_path / "static")) as client:
        saved = client.get("/api/tracks").json()
        assert len(saved) == 1
        assert saved[0]["title"] == "Gəlin — ж"
        assert saved[0]["status"] == "ready"


def test_queued_jobs_retry_guard_and_delete_cleanup(application, media, monkeypatch):
    client, app, directory = application
    runner = app.state.jobs
    monkeypatch.setattr(runner, "submit", lambda _: None)
    job = upload(client, ("song.wav", media["wav"]))[0]
    track_id = job["track_id"]
    queued = client.get(f"/api/jobs/{job['id']}").json()
    assert (queued["status"], queued["progress"]) == ("queued", 0)
    assert client.delete(f"/api/tracks/{track_id}").status_code == 409
    assert client.post(f"/api/tracks/{track_id}/retry").status_code == 409
    runner.fail(job["id"], "Temporary test import failure. Try again.")
    failed = client.get("/api/tracks").json()[0]
    assert failed["can_retry"]
    retry = client.post(f"/api/tracks/{track_id}/retry")
    assert retry.status_code == 202
    assert retry.json()["id"] != job["id"]
    assert client.post(f"/api/tracks/{track_id}/retry").status_code == 409
    runner.run_import(retry.json()["id"])
    track = finished(client)[0]
    assert track["status"] == "ready"
    assert len(list((directory / "originals").iterdir())) == 1
    assert client.delete(f"/api/tracks/{track_id}").status_code == 204
    assert client.get("/api/tracks").json() == []
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    for folder in ("originals", "work", "peaks"):
        assert list((directory / folder).iterdir()) == []


def test_interrupted_import_recovers_to_retryable_error(tmp_path, media, monkeypatch):
    directory = tmp_path / "data"
    app = create_app(data_dir=directory, static_dir=tmp_path / "static")
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.jobs, "submit", lambda _: None)
        job = upload(client, ("song.wav", media["wav"]))[0]
        assert job["status"] == "queued"
    with TestClient(create_app(data_dir=directory, static_dir=tmp_path / "static")) as client:
        track = client.get("/api/tracks").json()[0]
        assert track["status"] == "error"
        assert "interrupted" in track["error"]
        assert track["can_retry"]
        assert track["job"]["status"] == "error"
        assert client.post(f"/api/tracks/{track['id']}/retry").status_code == 202
        assert finished(client)[0]["status"] == "ready"


def test_missing_original_cannot_be_retried(application, monkeypatch):
    client, app, directory = application
    monkeypatch.setattr(app.state.jobs, "submit", lambda _: None)
    job = upload(client, ("corrupt.wav", b"not audio"))[0]
    app.state.jobs.fail(job["id"], "Could not read this file.")
    next((directory / "originals").iterdir()).unlink()
    track = client.get("/api/tracks").json()[0]
    assert track["can_retry"] is False
    response = client.post(f"/api/tracks/{track['id']}/retry")
    assert response.status_code == 409
    assert "Choose it again" in response.json()["detail"]


def test_invalid_and_missing_ids_and_missing_file_payload(application):
    client, _, _ = application
    unknown = str(uuid4())
    for path in (f"/api/tracks/{unknown}/audio", f"/api/tracks/{unknown}/peaks", f"/api/jobs/{unknown}"):
        assert client.get(path).status_code == 404
    assert client.get("/api/tracks/not-a-uuid/audio").status_code == 422
    assert client.get("/api/jobs/not-a-uuid").status_code == 422
    assert client.post("/api/tracks/upload").status_code == 422
