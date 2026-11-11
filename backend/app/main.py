from contextlib import asynccontextmanager
from pathlib import Path
import math

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError

from .api.system import router as system_router
from .api.tracks import router as tracks_router
from .api.jobs import router as jobs_router
from .api.projects import router as projects_router
from .api.youtube import router as youtube_router
from .api.exports import router as exports_router
from .database import Database
from .jobs import JobRunner
from .settings import DATA_DIR, STATIC_DIR


def create_app(static_dir: Path = STATIC_DIR, data_dir: Path = DATA_DIR) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(data_dir)
        app.state.database = database
        app.state.jobs = JobRunner(database)
        try:
            yield
        finally:
            app.state.jobs.close()
            database.engine.dispose()

    app = FastAPI(title="Wedding Mix Maker", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Invalid NaN/Infinity values can appear in Pydantic's error input;
        # keep the rejection itself JSON-safe instead of raising a second error.
        def safe(value):
            if isinstance(value, float) and not math.isfinite(value):
                return str(value)
            if isinstance(value, dict):
                return {key: safe(item) for key, item in value.items()}
            if isinstance(value, list):
                return [safe(item) for item in value]
            return value

        return JSONResponse(status_code=422, content={"detail": safe(jsonable_encoder(error.errors()))})
    app.include_router(system_router)
    app.include_router(tracks_router)
    app.include_router(jobs_router)
    app.include_router(projects_router)
    app.include_router(youtube_router)
    app.include_router(exports_router)

    # Keep unknown API routes JSON even when the frontend is mounted at /.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def unknown_api(path: str):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    if (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    else:
        @app.get("/", include_in_schema=False)
        def frontend_not_built():
            return JSONResponse(status_code=503, content={
                "message": "Frontend not built. Run make run, or use http://127.0.0.1:5173 with make dev.",
            })
    return app


app = create_app()

