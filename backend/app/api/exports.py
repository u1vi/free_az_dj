"""Snapshot-based export and transition preview jobs with persistent downloads."""

import shutil
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..audio.render import estimate_export_bytes, execute_export, execute_mix_preview, execute_preview, safe_title
from ..models import Clip, Job, JobRead, Project, Track

router = APIRouter(tags=["exports"])


class ExportOptions(BaseModel):
    format: Literal["mp3", "wav"] = "mp3"
    bitrate: Literal[192, 256, 320] = 320
    sample_rate: Literal[44100, 48000] = 44100
    bit_depth: Literal[16, 24] = 16
    also_separate_files: bool = False


class PreviewOptions(BaseModel):
    clip_index: int = Field(ge=0)


def project_snapshot(session: Session, database, project_id: str) -> tuple[Project, dict]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Mix not found.")
    clips = session.exec(select(Clip).where(Clip.project_id == project_id).order_by(Clip.position, Clip.id)).all()
    if not clips:
        raise HTTPException(400, "Add at least one song to the mix before exporting.")
    snapshot = {"settings": {"name": project.name, "normalize": project.normalize, "target_lufs": project.target_lufs}, "clips": []}
    for clip in clips:
        track = session.get(Track, clip.track_id)
        if not track or track.status != "ready" or not database.working(clip.track_id).is_file():
            raise HTTPException(409, "A song in this mix is unavailable. Check the Library before exporting.")
        snapshot["clips"].append({**clip.model_dump(), "path": str(database.working(track.id)), "title": track.title,
                                  "track_lufs": track.loudness_lufs})
    return project, snapshot


@router.post("/api/projects/{project_id}/export", response_model=JobRead, status_code=202)
def start_export(project_id: UUID, options: ExportOptions, request: Request):
    database, runner = request.app.state.database, request.app.state.jobs
    with runner.lock, Session(database.engine, expire_on_commit=False) as session:
        project, snapshot = project_snapshot(session, database, str(project_id))
        if project.export_job_id:
            previous = session.get(Job, project.export_job_id)
            if previous and previous.status in ("queued", "running"):
                raise HTTPException(409, "This mix is already exporting. Wait for it to finish.")
        if shutil.disk_usage(database.directory).free < estimate_export_bytes(snapshot["clips"], options.model_dump()):
            raise HTTPException(400, "Not enough disk space for this export. Free some space and try again.")
        # The dialog only offers a previous export's downloads while the saved mix is unchanged.
        job = Job(kind="export", track_id=project.id, message="Waiting to export",
                  result_json={"track_ids": [clip["track_id"] for clip in snapshot["clips"]],
                               "project_updated_at": project.updated_at.isoformat()})
        project.export_job_id = job.id
        session.add(job)
        session.add(project)
        session.commit()
        response = JobRead.model_validate(job)
        runner.submit_task(job.id, lambda update: execute_export(database, job.id, snapshot, options.model_dump(), update))
        return response


@router.post("/api/projects/{project_id}/preview-transition", response_model=JobRead, status_code=202)
def start_preview(project_id: UUID, options: PreviewOptions, request: Request):
    database, runner = request.app.state.database, request.app.state.jobs
    with runner.lock, Session(database.engine, expire_on_commit=False) as session:
        _, snapshot = project_snapshot(session, database, str(project_id))
        if options.clip_index >= len(snapshot["clips"]) - 1:
            raise HTTPException(400, "Choose a transition between two songs.")
        job = Job(kind="preview", track_id=str(project_id), message="Waiting for transition preview",
                  result_json={"track_ids": [clip["track_id"] for clip in snapshot["clips"][options.clip_index:options.clip_index + 2]]})
        session.add(job)
        session.commit()
        response = JobRead.model_validate(job)
        runner.submit_task(job.id, lambda update: execute_preview(database, job.id, snapshot, options.clip_index, update))
        return response


def prune_mix_previews(session: Session, database, project_id: str) -> None:
    """A full-mix preview can be tens of MB; keep only the newest finished one."""
    files = []
    for job in session.exec(select(Job).where(Job.kind == "preview", Job.track_id == project_id)).all():
        path = database.directory / "previews" / f"{job.id}.mp3"
        if (job.result_json or {}).get("full_mix") and job.status in ("done", "error") and path.is_file():
            files.append(path)
    for path in sorted(files, key=lambda item: item.stat().st_mtime)[:-1]:
        path.unlink(missing_ok=True)


@router.post("/api/projects/{project_id}/preview-mix", response_model=JobRead, status_code=202)
def start_mix_preview(project_id: UUID, request: Request):
    database, runner = request.app.state.database, request.app.state.jobs
    with runner.lock, Session(database.engine, expire_on_commit=False) as session:
        _, snapshot = project_snapshot(session, database, str(project_id))
        for job in session.exec(select(Job).where(Job.kind == "preview", Job.track_id == str(project_id),
                                                  Job.status.in_(["queued", "running"]))).all():
            if (job.result_json or {}).get("full_mix"):
                return JobRead.model_validate(job)
        prune_mix_previews(session, database, str(project_id))
        job = Job(kind="preview", track_id=str(project_id), message="Waiting for full mix preview",
                  result_json={"full_mix": True, "track_ids": [clip["track_id"] for clip in snapshot["clips"]]})
        session.add(job)
        session.commit()
        response = JobRead.model_validate(job)
        runner.submit_task(job.id, lambda update: execute_mix_preview(database, job.id, snapshot, update))
        return response


@router.get("/api/exports/{export_id}/download", response_class=FileResponse)
def download_export(export_id: UUID, request: Request, kind: Literal["mix", "tracklist", "separate", "preview"] = "mix"):
    database = request.app.state.database
    with Session(database.engine) as session:
        job = session.get(Job, str(export_id))
        if not job or job.kind not in ("export", "preview"):
            raise HTTPException(404, "Export not found.")
        if job.status != "done" or not job.result_json:
            raise HTTPException(409, "This export is not ready to download yet.")
        result = job.result_json
        if kind == "preview" and job.kind == "preview":
            path = database.directory / "previews" / f"{job.id}.mp3"
            return FileResponse(path, media_type="audio/mpeg") if path.is_file() else missing_download()
        if job.kind != "export":
            raise HTTPException(404, "This preview has no mix download.")
        extension = result.get("format", "mp3")
        if extension not in ("mp3", "wav"):
            raise HTTPException(404, "Export file not found.")
        if kind == "mix":
            path = database.directory / "exports" / f"{job.id}.{extension}"
            filename = safe_title(result.get("project_name", "Wedding mix")) + f".{extension}"
            media_type = "audio/mpeg" if extension == "mp3" else "audio/wav"
        elif kind == "tracklist":
            path, filename, media_type = database.directory / "exports" / f"{job.id}.txt", "tracklist.txt", "text/plain; charset=utf-8"
        elif kind == "separate" and result.get("separate_url"):
            path, filename, media_type = database.directory / "exports" / f"{job.id}.zip", "individual-songs.zip", "application/zip"
        else:
            raise HTTPException(404, "This download was not included in the export.")
        if not path.is_file():
            return missing_download()
        return FileResponse(path, filename=filename, media_type=media_type)


def missing_download():
    raise HTTPException(404, "The exported file is missing. Export the mix again.")
