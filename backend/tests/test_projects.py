import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.audio.ffprobe import AudioError
from app.main import create_app
from app.models import Job, Track


@pytest.fixture
def workspace(tmp_path):
    app = create_app(data_dir=tmp_path / "data", static_dir=tmp_path / "static")
    with TestClient(app) as client:
        with Session(app.state.database.engine, expire_on_commit=False) as session:
            first = Track(title="Gəlin", original_name="first.wav", original_suffix=".wav", status="ready", duration_s=10, loudness_lufs=-18, suggested_start_s=1, suggested_end_s=9)
            second = Track(title="Dance", original_name="second.wav", original_suffix=".wav", status="ready", duration_s=4)
            session.add(first)
            session.add(second)
            session.commit()
        yield client, app, first, second


def test_add_duplicate_trim_and_full_save_survive_restart(workspace, tmp_path):
    client, app, first, second = workspace
    project = client.get("/api/projects/default").json()
    assert project["clips"] == []
    for track in (first, second, first):
        response = client.post(f"/api/projects/{project['id']}/clips", json={"track_id": track.id})
        assert response.status_code == 200, response.text
        project = response.json()
    assert [clip["position"] for clip in project["clips"]] == [0, 1, 2]
    assert len({clip["id"] for clip in project["clips"]}) == 3
    assert project["clips"][0]["start_s"] == 1
    assert project["clips"][0]["end_s"] == 9
    project["clips"] = list(reversed(project["clips"]))
    project["clips"][0]["start_s"] = 2.125
    project["clips"][0]["end_s"] = 8.875
    project["clips"][0]["transition"] = "gap"
    project["clips"][0]["transition_s"] = 0.25
    project["name"] = "Toy — ж"
    response = client.put(f"/api/projects/{project['id']}", json=project)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["name"] == "Toy — ж"
    assert saved["clips"][0]["start_s"] == 2.125
    assert saved["clips"][0]["end_s"] == 8.875
    assert [clip["position"] for clip in saved["clips"]] == [0, 1, 2]
    with TestClient(create_app(data_dir=tmp_path / "data", static_dir=tmp_path / "static")) as reopened:
        restored = reopened.get("/api/projects/default").json()
        assert restored == saved


def test_clamps_oversized_trims_fades_gains_and_crossfades(workspace):
    client, _, first, second = workspace
    payload = {"name": "Mix", "clips": [
        {"track_id": first.id, "start_s": -5, "end_s": 1000, "fade_in_s": 99, "fade_out_s": -2, "gain_db": 99, "transition_s": 999},
        {"track_id": second.id, "start_s": 1, "end_s": 3, "transition": "cut"},
    ]}
    response = client.put("/api/projects/default", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    clip = data["clips"][0]
    assert (clip["start_s"], clip["end_s"], clip["fade_in_s"], clip["fade_out_s"], clip["gain_db"], clip["transition_s"]) == (0, 10, 10, 0, 12, 1)
    assert data["warnings"]


def test_invalid_clip_ids_missing_tracks_and_nonfinite_fields(workspace):
    client, _, first, _ = workspace
    identifier = str(uuid4())
    clip = {"id": identifier, "track_id": first.id, "start_s": 0, "end_s": 3}
    assert client.put("/api/projects/default", json={"name": "Mix", "clips": [clip, clip]}).status_code == 422
    assert client.post("/api/projects/default/clips", json={"track_id": str(uuid4())}).status_code == 409
    assert client.get("/api/projects/not-an-id").status_code == 422
    assert client.get(f"/api/projects/{uuid4()}").status_code == 404
    assert client.put("/api/projects/default", json={"name": "  ", "clips": []}).status_code == 422
    payload = json.dumps({"name": "Mix", "clips": [{**clip, "end_s": float("nan")}]})
    assert client.put("/api/projects/default", content=payload, headers={"content-type": "application/json"}).status_code == 422


def test_used_track_requires_force_and_removes_references(workspace):
    client, _, first, second = workspace
    for track in (first, second, first):
        assert client.post("/api/projects/default/clips", json={"track_id": track.id}).status_code == 200
    assert client.delete(f"/api/tracks/{first.id}").status_code == 409
    assert client.delete(f"/api/tracks/{first.id}?force=true").status_code == 204
    clips = client.get("/api/projects/default").json()["clips"]
    assert len(clips) == 1 and clips[0]["track_id"] == second.id and clips[0]["position"] == 0


def test_active_render_blocks_even_forced_track_deletion(workspace):
    client, app, first, _ = workspace
    with Session(app.state.database.engine) as session:
        session.add(Job(track_id="project", kind="export", status="running", result_json={"track_ids": [first.id]}))
        session.commit()
    assert client.delete(f"/api/tracks/{first.id}?force=true").status_code == 409


def test_failed_export_does_not_mark_its_source_track_as_failed(workspace):
    client, app, first, _ = workspace
    with Session(app.state.database.engine, expire_on_commit=False) as session:
        job = Job(track_id=first.id, kind="export")
        session.add(job)
        session.commit()

    def failure(update):
        raise AudioError("Test render failure")

    app.state.jobs.run_task(job.id, failure)
    assert client.get(f"/api/jobs/{job.id}").json()["status"] == "error"
    assert next(track for track in client.get("/api/tracks").json() if track["id"] == first.id)["status"] == "ready"


def test_export_records_the_saved_mix_version_it_renders(workspace):
    client, app, first, _ = workspace
    project = client.get("/api/projects/default").json()
    project = client.post(f"/api/projects/{project['id']}/clips", json={"track_id": first.id}).json()
    app.state.database.working(first.id).write_bytes(b"audio")
    app.state.jobs.submit_task = lambda *_: None
    response = client.post(f"/api/projects/{project['id']}/export", json={"format": "wav"})
    assert response.status_code == 202, response.text
    assert response.json()["result_json"]["project_updated_at"] == project["updated_at"]
