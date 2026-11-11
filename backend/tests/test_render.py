"""Render real generated tones and verify the resulting audio, not just argv."""

import hashlib
import shutil
import subprocess
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.audio.ffprobe import probe
from app.audio.loudness import measure
from app.audio.render import (build_render_graph, estimate_export_bytes, execute_export,
                              execute_mix_preview, execute_preview, preview_snapshot, render_audio,
                              render_timeline, tracklist_text)
from app.audio.timeline import timeline
from app.database import Database


def clip(path="/audio/test.wav", **values):
    return {"path": str(path), "track_id": "track", "title": "Toy ə — ж", "start_s": 0, "end_s": 6,
            "track_lufs": -14, "gain_db": 0, "fade_in_s": 0.5, "fade_out_s": 2,
            "transition": "crossfade", "transition_s": 1, **values}


@pytest.mark.parametrize("kind,seconds,offset,total", [("crossfade", 2, 4, 10), ("gap", 2, 8, 14), ("cut", 9, 6, 12)])
def test_timeline_transition_math(kind, seconds, offset, total):
    result = timeline([clip(transition=kind, transition_s=seconds), clip()])
    assert result["offsets"] == [0, offset]
    assert result["total"] == total


def test_timeline_clamps_each_neighbor_and_handles_empty():
    result = timeline([clip(end_s=6, transition_s=10), clip(end_s=2), clip(end_s=8)])
    assert result["transitions"] == [1, 1]
    assert result["offsets"] == [0, 5, 6]
    assert result["total"] == 14
    assert len(result["warnings"]) == 1
    assert timeline([])["total"] == 0
    with pytest.raises(ValueError):
        timeline([clip(start_s=6, end_s=6)])


def test_single_clip_graph_snapshot_and_boost_limit():
    inputs, graph = build_render_graph([clip(track_lufs=-40)], {"normalize": True, "target_lufs": -14})
    assert inputs == ["-ss", "0", "-t", "6", "-i", "/audio/test.wav"]
    assert graph == (
        "[0:a]atrim=duration=6,asetpts=PTS-STARTPTS,volume=12dB,afade=t=in:d=0.5,afade=t=out:st=4:d=2,"
        "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[c0];\n"
        "[c0]aresample=192000,alimiter=limit=0.84:level=false:latency=true,aresample=44100[out]"
    )


@pytest.mark.parametrize("kind,join,snapshot", [
    ("crossfade", "acrossfade=d=1:c1=qsin:c2=qsin", "af3d97ae7b688a6fb91c45d05714aef919af60b2d3dd13de20f44e3eef63ba95"),
    ("gap", "concat=n=3:v=0:a=1", "548762f3d670b7acdc224c690c29f3c2da53ebb2d0067b6eeeaefd3b16bdab43"),
    ("cut", "concat=n=2:v=0:a=1", "280f0cce604f36f63576567186d5f739451cf2cab1f9551e7aa4743746bc88a5"),
])
def test_two_clip_graph_fades_and_all_join_types(kind, join, snapshot):
    _, graph = build_render_graph([clip(transition=kind), clip()], {"normalize": False})
    assert join in graph
    assert graph.count("afade=") == (2 if kind == "crossfade" else 4)
    if kind == "gap":
        assert "anullsrc=r=44100:cl=stereo,atrim=duration=1" in graph
    assert graph.endswith("aresample=44100[out]")
    assert hashlib.sha256(graph.encode()).hexdigest() == snapshot


def test_five_clip_graph_is_deterministic_and_has_one_output_limiter():
    clips = [clip(path=f"/audio/{index}.wav", transition=kind) for index, kind in enumerate(["crossfade", "gap", "cut", "crossfade", "cut"])]
    first = build_render_graph(clips, {"normalize": True})
    assert first == build_render_graph(clips, {"normalize": True})
    assert first[1].count("alimiter=") == 1
    assert first[1].count("acrossfade=") == 2
    assert first[1].count("concat=") == 2
    assert len(first[0]) == 5 * 6
    assert hashlib.sha256(first[1].encode()).hexdigest() == "6f12df2e18fcca6e239ca3adce935c14856779cf8dc3cc729f9f156157891082"


def test_tracklist_has_real_offsets_and_safe_lines():
    clips = [clip(end_s=1000, transition_s=4, title="Gəlin\nDance"), clip(end_s=60, title="Жених")]
    assert tracklist_text(clips) == "00:00:00  Gəlin Dance\n00:16:36  Жених\n"


@pytest.fixture(scope="module")
def tones(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for generated-audio render checks")
    folder = tmp_path_factory.mktemp("render-tones")
    paths = []
    for index, gain in enumerate(("2", "0.632455532")):
        path = folder / f"tone-{index}.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=30",
                        "-af", f"volume={gain}", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(path)], check=True, capture_output=True)
        paths.append((path, measure(path, 30)[0]))
    return paths


@pytest.mark.parametrize("format", ["wav", "mp3"])
def test_three_clip_export_matches_timeline_and_peak_limit(tmp_path, tones, format):
    database = Database(tmp_path / "data")
    snapshot = {"clips": [clip(tones[0][0], start_s=2, end_s=8, track_lufs=tones[0][1]),
                           clip(tones[1][0], start_s=1, end_s=7, track_lufs=tones[1][1], transition="gap", transition_s=0.5),
                           clip(tones[0][0], end_s=4, track_lufs=tones[0][1])],
                "settings": {"name": "Toy ə — ж", "normalize": True, "target_lufs": -14}}
    try:
        result = execute_export(database, f"three-{format}", snapshot, {"format": format, "bitrate": 320}, lambda *_: None)
        output = database.directory / "exports" / f"three-{format}.{format}"
        assert probe(output)["duration"] == pytest.approx(timeline(snapshot["clips"])["total"], abs=0.05)
        assert result["true_peak_db"] <= -1
        assert result["duration_s"] == 15.5
        assert (database.directory / "exports" / f"three-{format}.txt").read_text() == tracklist_text(snapshot["clips"])
    finally:
        database.engine.dispose()


def test_normalization_brings_tones_ten_db_apart_within_one_lu(tmp_path, tones):
    assert tones[0][1] - tones[1][1] == pytest.approx(10, abs=0.1)
    measured = []
    for index, (path, loudness) in enumerate(tones):
        output = tmp_path / f"normalized-{index}.wav"
        render_audio([clip(path, track_lufs=loudness, fade_in_s=0, fade_out_s=0)], {"normalize": True, "target_lufs": -14}, output, {"format": "wav"})
        measured.append(measure(output, 6)[0])
    assert abs(measured[0] - measured[1]) <= 1


def test_limiter_prevents_clipping_after_large_gain(tmp_path, tones):
    output = tmp_path / "limited.mp3"
    render_audio([clip(tones[0][0], gain_db=12, fade_in_s=0, fade_out_s=0)], {"normalize": False}, output, {"format": "mp3", "bitrate": 320})
    assert measure(output, 6)[1] <= -1


def test_advanced_wav_and_individual_zip_preserve_unicode_safely(tmp_path, tones):
    database = Database(tmp_path / "data")
    snapshot = {"clips": [clip(tones[0][0], end_s=2, title="../Gəlin: ж", transition="cut"), clip(tones[1][0], end_s=2)],
                "settings": {"name": "Toy", "normalize": False}}
    try:
        result = execute_export(database, "advanced", snapshot, {"format": "wav", "sample_rate": 48000, "bit_depth": 24, "also_separate_files": True}, lambda *_: None)
        audio = probe(database.directory / "exports" / "advanced.wav")["audio"]
        assert audio["sample_rate"] == "48000"
        assert audio["bits_per_sample"] == 24
        assert result["separate_url"].endswith("kind=separate")
        with zipfile.ZipFile(database.directory / "exports" / "advanced.zip") as archive:
            assert len(archive.namelist()) == 2
            assert all("/" not in name and "\\" not in name for name in archive.namelist())
            assert "Gəlin" in archive.namelist()[0]
    finally:
        database.engine.dispose()


def test_transition_preview_preserves_real_long_crossfade_and_finishes_quickly(tmp_path, tones):
    database = Database(tmp_path / "data")
    snapshot = {"clips": [clip(tones[0][0], end_s=30, transition_s=9), clip(tones[1][0], end_s=30)], "settings": {"normalize": False}}
    cropped = preview_snapshot(snapshot, 0)
    assert cropped["clips"][0]["start_s"] == 18
    assert cropped["clips"][1]["end_s"] == 12
    assert render_timeline(cropped["clips"], cropped["settings"])["total"] == 15
    assert "acrossfade=d=9:" in build_render_graph(cropped["clips"], cropped["settings"])[1]
    started = time.monotonic()
    try:
        result = execute_preview(database, "preview", snapshot, 0, lambda *_: None)
        elapsed = time.monotonic() - started
        assert result["duration_s"] == 15
        assert probe(database.directory / "previews" / "preview.mp3")["duration"] == pytest.approx(15, abs=0.05)
        assert elapsed < 2, f"Preview rendering took {elapsed:.2f}s"
    finally:
        database.engine.dispose()


def test_export_space_estimate_includes_backups_and_output_correction():
    clips = [clip(end_s=60)]
    base = estimate_export_bytes(clips, {"format": "wav"})
    backup = estimate_export_bytes(clips, {"format": "wav", "also_separate_files": True})
    assert base > 60 * 44100 * 4
    assert backup > base


def test_export_api_job_download_and_empty_mix_rejection(tmp_path, tones):
    from app.main import create_app
    from app.models import Clip, Project, Track
    app = create_app(data_dir=tmp_path / "data", static_dir=tmp_path / "static")
    with TestClient(app) as client:
        with Session(app.state.database.engine, expire_on_commit=False) as session:
            project = Project(name="Test export")
            track = Track(title="Gəlin", original_name="song.wav", original_suffix=".wav", status="ready", duration_s=30, loudness_lufs=tones[0][1])
            session.add(project)
            session.add(track)
            session.commit()
            project_id, track_id = project.id, track.id
        assert client.post(f"/api/projects/{project_id}/export", json={}).status_code == 400
        shutil.copyfile(tones[0][0], app.state.database.working(track_id))
        with Session(app.state.database.engine) as session:
            session.add(Clip(project_id=project_id, track_id=track_id, position=0, start_s=1, end_s=4))
            session.commit()
        response = client.post(f"/api/projects/{project_id}/export", json={"format": "wav", "also_separate_files": True})
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job["status"] == "done", job
        for kind in ("mix", "tracklist", "separate"):
            download = client.get(f"/api/exports/{job_id}/download?kind={kind}")
            assert download.status_code == 200, download.text
            assert download.content
        assert client.get(f"/api/exports/{job_id}/download?kind=preview").status_code == 404


def test_full_mix_preview_matches_export_timeline_and_lists_song_starts(tmp_path, tones):
    database = Database(tmp_path / "data")
    snapshot = {"clips": [clip(tones[0][0], start_s=2, end_s=8, track_lufs=tones[0][1], title="Gəlin"),
                          clip(tones[1][0], start_s=1, end_s=7, track_lufs=tones[1][1], transition="gap", transition_s=0.5),
                          clip(tones[0][0], end_s=4, track_lufs=tones[0][1])],
                "settings": {"name": "Toy", "normalize": True, "target_lufs": -14}}
    try:
        result = execute_mix_preview(database, "full", snapshot, lambda *_: None)
        assert result["duration_s"] == timeline(snapshot["clips"])["total"] == 15.5
        assert probe(database.directory / "previews" / "full.mp3")["duration"] == pytest.approx(15.5, abs=0.05)
        assert [song["start_s"] for song in result["songs"]] == [0, 5, 11.5]
        assert result["songs"][0]["title"] == "Gəlin"
        assert result["preview_url"] == "/api/exports/full/download?kind=preview"
    finally:
        database.engine.dispose()


def test_full_mix_preview_api_reuses_running_job_and_prunes_old_previews(tmp_path, tones):
    from app.main import create_app
    from app.models import Clip, Job, Project, Track
    app = create_app(data_dir=tmp_path / "data", static_dir=tmp_path / "static")
    with TestClient(app) as client:
        database = app.state.database
        with Session(database.engine, expire_on_commit=False) as session:
            project = Project(name="Preview")
            track = Track(title="Song", original_name="song.wav", original_suffix=".wav", status="ready", duration_s=30, loudness_lufs=tones[0][1])
            session.add(project)
            session.add(track)
            session.commit()
            project_id, track_id = project.id, track.id
        assert client.post(f"/api/projects/{project_id}/preview-mix").status_code == 400
        shutil.copyfile(tones[0][0], database.working(track_id))
        with Session(database.engine) as session:
            session.add(Clip(project_id=project_id, track_id=track_id, position=0, start_s=1, end_s=4))
            session.add(Clip(project_id=project_id, track_id=track_id, position=1, start_s=5, end_s=9))
            # Two finished older previews: only the newest one should survive a new render.
            for name in ("old-a", "old-b"):
                session.add(Job(id=name, kind="preview", track_id=project_id, status="done", result_json={"full_mix": True}))
                (database.directory / "previews" / f"{name}.mp3").write_bytes(b"x")
                time.sleep(0.01)
            # A running preview is returned instead of starting a second render.
            session.add(Job(id="busy", kind="preview", track_id=project_id, status="running", result_json={"full_mix": True}))
            session.commit()
        assert client.post(f"/api/projects/{project_id}/preview-mix").json()["id"] == "busy"
        with Session(database.engine) as session:
            session.get(Job, "busy").status = "done"
            session.commit()
        response = client.post(f"/api/projects/{project_id}/preview-mix")
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        assert not (database.directory / "previews" / "old-a.mp3").exists()
        assert (database.directory / "previews" / "old-b.mp3").exists()
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job["status"] == "done", job
        assert [song["start_s"] for song in job["result_json"]["songs"]] == [0, 1.5]
        audio = client.get(job["result_json"]["preview_url"], headers={"Range": "bytes=0-99"})
        assert audio.status_code == 206
        assert len(audio.content) == 100
