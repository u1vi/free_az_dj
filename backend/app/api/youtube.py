from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..audio.ffprobe import AudioError
from ..importers.youtube import LONG_VIDEO_WARNING, parse_url, playlist_entries
from ..models import Job, JobRead, Track

router = APIRouter(prefix="/api/tracks", tags=["tracks"])


class YouTubeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    playlist: list[str] | None = Field(default=None, max_length=1000)


class PlaylistEntry(BaseModel):
    url: str
    title: str
    duration_s: float | None


class YouTubeResponse(BaseModel):
    jobs: list[JobRead] = Field(default_factory=list)
    playlist: list[PlaylistEntry] | None = None
    warning: str | None = None


@router.post("/youtube", response_model=YouTubeResponse)
def import_youtube(payload: YouTubeRequest, request: Request, response: Response):
    try:
        parsed = parse_url(payload.url)
        if payload.playlist is None and parsed.is_playlist:
            entries = playlist_entries(parsed.url)
            warning = LONG_VIDEO_WARNING if any((entry["duration_s"] or 0) > 1200 for entry in entries) else None
            return YouTubeResponse(playlist=[PlaylistEntry(**entry) for entry in entries], warning=warning)
        if payload.playlist is not None:
            if not payload.playlist:
                raise AudioError("Select at least one video from the playlist.")
            selected = [parse_url(url) for url in payload.playlist]
            if any(item.is_playlist for item in selected):
                raise AudioError("Select individual videos from the playlist.")
            urls = list(dict.fromkeys(item.url for item in selected))
        else:
            urls = [parsed.url]
    except AudioError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    database, runner = request.app.state.database, request.app.state.jobs
    jobs = []
    for url in urls:
        track = Track(title="YouTube video", source_type="youtube", source_url=url,
                      original_name="YouTube video", original_suffix=".pending")
        job = Job(track_id=track.id, kind="import_youtube", message="Waiting for YouTube download")
        track.job_id = job.id
        with Session(database.engine, expire_on_commit=False) as session:
            session.add(track)
            session.add(job)
            session.commit()
            jobs.append(JobRead.model_validate(job))
        runner.submit(job.id)
    response.status_code = 202
    return YouTubeResponse(jobs=jobs)
