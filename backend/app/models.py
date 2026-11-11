"""Durable songs, projects, clips, and background jobs."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Track(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    source_type: str = "upload"
    source_url: str | None = None
    original_name: str
    original_suffix: str
    duration_s: float | None = None
    loudness_lufs: float | None = None
    true_peak_db: float | None = None
    suggested_start_s: float = 0
    suggested_end_s: float | None = None
    status: str = Field(default="importing", index=True)
    error: str | None = None
    job_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    track_id: str = Field(index=True)
    kind: str = "import_upload"
    status: str = Field(default="queued", index=True)
    progress: float = 0
    message: str = "Waiting to import"
    result_json: dict | None = Field(default=None, sa_column=Column(JSON))


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    track_id: str
    kind: str
    status: str
    progress: float
    message: str
    result_json: dict | None


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    original_name: str
    source_type: str
    source_url: str | None
    duration_s: float | None
    loudness_lufs: float | None
    true_peak_db: float | None
    suggested_start_s: float
    suggested_end_s: float | None
    status: str
    error: str | None
    created_at: datetime
    job: JobRead | None = None
    can_retry: bool = False


DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


class Project(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = "Wedding mix"
    default_crossfade_s: float = 4
    normalize: bool = True
    target_lufs: float = -14
    export_job_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Clip(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    track_id: str = Field(foreign_key="track.id", index=True)
    position: int
    start_s: float = 0
    end_s: float
    fade_in_s: float = 0.5
    fade_out_s: float = 2
    gain_db: float = 0
    transition: str = "crossfade"
    transition_s: float = 4
