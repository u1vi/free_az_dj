from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session

from ..models import Job, JobRead

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, request: Request):
    with Session(request.app.state.database.engine) as session:
        job = session.get(Job, str(job_id))
        if not job:
            raise HTTPException(404, "Import job not found.")
        return JobRead.model_validate(job)
