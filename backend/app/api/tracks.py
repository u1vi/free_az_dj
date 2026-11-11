import errno
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from ..models import Clip, Job, JobRead, Project, Track, TrackRead

router = APIRouter(prefix="/api/tracks", tags=["tracks"])
logger = logging.getLogger(__name__)


class RenameTrack(BaseModel):
    title: str = Field(min_length=1, max_length=300)

    @field_validator("title")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the song a name.")
        return value.strip()


def require_track(session: Session, track_id: UUID) -> Track:
    track = session.get(Track, str(track_id))
    if not track:
        raise HTTPException(404, "Song not found.")
    return track


def public_track(track: Track, job: Job | None, database) -> TrackRead:
    result = TrackRead.model_validate(track)
    result.job = JobRead.model_validate(job) if job else None
    result.can_retry = track.status == "error" and (track.source_type == "youtube" or database.original(track).is_file())
    return result


@router.get("", response_model=list[TrackRead])
def list_tracks(request: Request):
    database = request.app.state.database
    with Session(database.engine) as session:
        tracks = session.exec(select(Track).order_by(Track.created_at, Track.id)).all()
        jobs = {job.id: job for job in session.exec(select(Job).where(Job.id.in_([track.job_id for track in tracks if track.job_id])))}
        return [public_track(track, jobs.get(track.job_id), database) for track in tracks]


@router.post("/upload", response_model=list[JobRead], status_code=202)
def upload_tracks(request: Request, files: list[UploadFile] = File(...)):
    database, runner = request.app.state.database, request.app.state.jobs
    result = []
    for upload in files:
        name = Path((upload.filename or "Untitled").replace("\\", "/")).name[:1000] or "Untitled"
        suffix = Path(name).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ".bin"
        track = Track(title=Path(name).stem[:300] or name[:300], original_name=name, original_suffix=suffix)
        job = Job(track_id=track.id)
        track.job_id = job.id
        with Session(database.engine, expire_on_commit=False) as session:
            session.add(track)
            session.add(job)
            session.commit()
        temporary = database.original(track).with_suffix(".part")
        try:
            with temporary.open("wb") as destination:
                shutil.copyfileobj(upload.file, destination, length=1024 * 1024)
            temporary.replace(database.original(track))
            runner.submit(job.id)
        except OSError as error:
            message = "Not enough disk space. Free some space and choose this file again." if error.errno == errno.ENOSPC else "Could not save this file. Check disk permissions and choose it again."
            runner.fail(job.id, message)
        finally:
            upload.file.close()
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove incomplete upload %s", track.id)
        with Session(database.engine) as session:
            result.append(JobRead.model_validate(session.get(Job, job.id)))
    return result


@router.post("/{track_id}/retry", response_model=JobRead, status_code=202)
def retry_track(track_id: UUID, request: Request):
    database, runner = request.app.state.database, request.app.state.jobs
    # Serialize status checks with creation so a double click cannot start two jobs.
    with runner.lock, Session(database.engine) as session:
        track = require_track(session, track_id)
        if track.status != "error":
            raise HTTPException(409, "Only failed imports can be retried.")
        if track.source_type != "youtube" and not database.original(track).is_file():
            raise HTTPException(409, "The original file is missing. Choose it again to import.")
        job = Job(track_id=track.id, kind="import_youtube" if track.source_type == "youtube" else "import_upload")
        track.status, track.error, track.job_id = "importing", None, job.id
        session.add(track)
        session.add(job)
        session.commit()
        session.refresh(job)
        response = JobRead.model_validate(job)
        runner.submit(job.id)
        return response


@router.patch("/{track_id}", response_model=TrackRead)
def rename_track(track_id: UUID, payload: RenameTrack, request: Request):
    database = request.app.state.database
    with Session(database.engine) as session:
        track = require_track(session, track_id)
        track.title = payload.title
        session.add(track)
        session.commit()
        session.refresh(track)
        return public_track(track, session.get(Job, track.job_id), database)


@router.delete("/{track_id}", status_code=204)
def delete_track(track_id: UUID, request: Request, force: bool = False):
    database, runner = request.app.state.database, request.app.state.jobs
    with runner.lock, Session(database.engine) as session:
        track = require_track(session, track_id)
        if track.status == "importing":
            raise HTTPException(409, "Wait for this import to finish before removing the song.")
        references = session.exec(select(Clip).where(Clip.track_id == track.id)).all()
        if references and not force:
            raise HTTPException(409, "This song is used in the mix. Remove its clips first.")
        for job in session.exec(select(Job).where(Job.status.in_(["queued", "running"]))):
            if job.kind in ("export", "preview") and track.id in (job.result_json or {}).get("track_ids", []):
                raise HTTPException(409, "This song is being rendered. Wait for the export or preview to finish.")
        affected = {clip.project_id for clip in references}
        for clip in references:
            session.delete(clip)
        session.flush()
        for project_id in affected:
            for position, clip in enumerate(session.exec(select(Clip).where(Clip.project_id == project_id).order_by(Clip.position))):
                clip.position = position
                session.add(clip)
            project = session.get(Project, project_id)
            project.updated_at = datetime.now(timezone.utc)
            session.add(project)
        for job in session.exec(select(Job).where(Job.track_id == track.id)).all():
            session.delete(job)
        for folder in ("originals", "work", "peaks"):
            for path in (database.directory / folder).glob(f"{track.id}.*"):
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
        session.delete(track)
        session.commit()
    return Response(status_code=204)


@router.get("/{track_id}/audio", response_class=FileResponse)
def track_audio(track_id: UUID, request: Request):
    database = request.app.state.database
    with Session(database.engine) as session:
        track = require_track(session, track_id)
        if track.status != "ready" or not database.working(track.id).is_file():
            raise HTTPException(409, "This song is not ready for playback yet.")
    return FileResponse(database.working(str(track_id)), media_type="audio/wav")


@router.get("/{track_id}/peaks", response_class=FileResponse)
def track_peaks(track_id: UUID, request: Request):
    database = request.app.state.database
    with Session(database.engine) as session:
        track = require_track(session, track_id)
        if track.status != "ready" or not database.peaks(track.id).is_file():
            raise HTTPException(409, "The waveform is not ready yet.")
    return FileResponse(database.peaks(str(track_id)), media_type="application/json")
