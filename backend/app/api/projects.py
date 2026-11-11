from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, FiniteFloat, field_validator
from sqlmodel import Session, select

from ..models import DEFAULT_PROJECT_ID, Clip, Project, Track, TrackRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ClipInput(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    track_id: UUID
    start_s: FiniteFloat = 0
    end_s: FiniteFloat
    fade_in_s: FiniteFloat = 0.5
    fade_out_s: FiniteFloat = 2
    gain_db: FiniteFloat = 0
    transition: Literal["crossfade", "gap", "cut"] = "crossfade"
    transition_s: FiniteFloat = 4


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    default_crossfade_s: FiniteFloat = 4
    normalize: bool = True
    target_lufs: FiniteFloat = -14
    clips: list[ClipInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the mix a name.")
        return value.strip()


class AddClip(BaseModel):
    track_id: UUID


def project_key(value: str) -> str:
    if value == "default":
        return DEFAULT_PROJECT_ID
    try:
        return str(UUID(value))
    except ValueError:
        raise HTTPException(422, "Invalid mix ID.") from None


def require_project(session: Session, value: str) -> Project:
    project = session.get(Project, project_key(value))
    if project is None:
        raise HTTPException(404, "Mix not found.")
    return project


def project_response(session: Session, project: Project, warnings: list[str] | None = None) -> dict:
    result = project.model_dump()
    result["warnings"] = warnings or []
    result["clips"] = []
    for clip in session.exec(select(Clip).where(Clip.project_id == project.id).order_by(Clip.position)):
        track = session.get(Track, clip.track_id)
        if track:
            result["clips"].append({**clip.model_dump(), "track": TrackRead.model_validate(track).model_dump()})
    return result


def validate_clips(session: Session, payload: list[ClipInput], project_id: str) -> tuple[list[dict], list[str]]:
    warnings = []
    result = []
    seen = set()
    for position, item in enumerate(payload):
        identifier = str(item.id)
        if identifier in seen:
            raise HTTPException(422, "Each clip needs a different ID. Duplicate a song using a new clip ID.")
        seen.add(identifier)
        previous = session.get(Clip, identifier)
        if previous and previous.project_id != project_id:
            raise HTTPException(409, "This clip belongs to another mix.")
        track = session.get(Track, str(item.track_id))
        if not track or track.status != "ready" or not track.duration_s:
            raise HTTPException(409, "A song in this mix is missing or still importing. Wait for the import to finish.")
        minimum = min(0.001, track.duration_s)
        start = min(max(0, item.start_s), track.duration_s - minimum)
        end = min(track.duration_s, max(start + minimum, item.end_s))
        length = end - start
        values = {
            "id": identifier, "project_id": project_id, "track_id": track.id, "position": position,
            "start_s": start, "end_s": end,
            "fade_in_s": min(length, 10, max(0, item.fade_in_s)),
            "fade_out_s": min(length, 10, max(0, item.fade_out_s)),
            "gain_db": min(12, max(-12, item.gain_db)), "transition": item.transition,
            "transition_s": max(0, item.transition_s),
        }
        if any(values[key] != getattr(item, key) for key in ("start_s", "end_s", "fade_in_s", "fade_out_s", "gain_db", "transition_s")):
            warnings.append(f"Clip {position + 1}: adjusted trim, fade, or gain to fit the song.")
        result.append(values)
    for index, clip in enumerate(result[:-1]):
        if clip["transition"] == "crossfade":
            following = result[index + 1]
            maximum = min((clip["end_s"] - clip["start_s"]) / 2, (following["end_s"] - following["start_s"]) / 2)
            if clip["transition_s"] > maximum:
                clip["transition_s"] = maximum
                warnings.append(f"Transition {index + 1}: shortened the crossfade to {maximum:g} seconds to fit both clips.")
    return result, warnings


@router.get("/{project_id}")
def get_project(project_id: str, request: Request):
    with Session(request.app.state.database.engine) as session:
        return project_response(session, require_project(session, project_id))


@router.put("/{project_id}")
def save_project(project_id: str, payload: ProjectInput, request: Request):
    with request.app.state.jobs.lock, Session(request.app.state.database.engine) as session:
        project = require_project(session, project_id)
        clips, warnings = validate_clips(session, payload.clips, project.id)
        identifiers = {clip["id"] for clip in clips}
        for previous in session.exec(select(Clip).where(Clip.project_id == project.id)).all():
            if previous.id not in identifiers:
                session.delete(previous)
        for values in clips:
            clip = session.get(Clip, values["id"])
            if clip is None:
                clip = Clip(**values)
            else:
                for key, value in values.items():
                    setattr(clip, key, value)
            session.add(clip)
        project.name = payload.name
        project.default_crossfade_s = max(0, payload.default_crossfade_s)
        project.normalize = payload.normalize
        project.target_lufs = min(-6, max(-36, payload.target_lufs))
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        session.refresh(project)
        return project_response(session, project, warnings)


@router.post("/{project_id}/clips")
def add_clip(project_id: str, payload: AddClip, request: Request):
    with request.app.state.jobs.lock, Session(request.app.state.database.engine) as session:
        project = require_project(session, project_id)
        track = session.get(Track, str(payload.track_id))
        if not track or track.status != "ready" or not track.duration_s:
            raise HTTPException(409, "Wait for this song to finish importing before adding it to the mix.")
        existing = session.exec(select(Clip).where(Clip.project_id == project.id).order_by(Clip.position)).all()
        new = ClipInput(track_id=UUID(track.id), start_s=track.suggested_start_s,
                        end_s=track.suggested_end_s or track.duration_s, transition_s=project.default_crossfade_s)
        clips, warnings = validate_clips(session, [*[ClipInput.model_validate(clip.model_dump()) for clip in existing], new], project.id)
        for values in clips:
            clip = session.get(Clip, values["id"]) or Clip(**values)
            for key, value in values.items():
                setattr(clip, key, value)
            session.add(clip)
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        session.refresh(project)
        return project_response(session, project, warnings)
