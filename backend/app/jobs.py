import errno
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select

from .audio.ffprobe import AudioError
from .database import Database
from .importers.upload import import_original
from .models import Job, Track

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, database: Database):
        self.database = database
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audio-import")
        self.render_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audio-render")
        self.lock = threading.Lock()
        # A process restart cannot resume an ffmpeg process. Keep originals for retry.
        with Session(database.engine) as session:
            for job in session.exec(select(Job).where(Job.status.in_(["queued", "running"]))):
                job.status = "error"
                job.message = "Import was interrupted when the app stopped. Try again." if job.kind.startswith("import_") else "Rendering was interrupted when the app stopped. Export or preview again."
                session.add(job)
                track = session.get(Track, job.track_id)
                if track and track.status == "importing":
                    track.status, track.error = "error", job.message
                    session.add(track)
            session.commit()

    def close(self) -> None:
        self.executor.shutdown(wait=True)
        self.render_executor.shutdown(wait=True)

    def submit(self, job_id: str) -> None:
        self.executor.submit(self.run_import, job_id)

    def submit_task(self, job_id: str, callback: Callable) -> None:
        self.render_executor.submit(self.run_task, job_id, callback)

    def run_task(self, job_id: str, callback: Callable) -> None:
        last_update = 0.0

        def update(progress: float, message: str) -> None:
            nonlocal last_update
            now = time.monotonic()
            if progress not in (0, 1) and now - last_update < 0.3:
                return
            with Session(self.database.engine) as session:
                job = session.get(Job, job_id)
                if job:
                    job.status, job.progress, job.message = "running", min(1, max(0, progress)), message
                    session.add(job)
                    session.commit()
            last_update = now

        try:
            update(0, "Preparing audio")
            result = callback(update)
            with Session(self.database.engine) as session:
                job = session.get(Job, job_id)
                if job:
                    job.status, job.progress, job.message = "done", 1, "Ready"
                    job.result_json = {**(job.result_json or {}), **result}
                    session.add(job)
                    session.commit()
        except AudioError as error:
            self.fail(job_id, str(error))
        except OSError as error:
            self.fail(job_id, "Not enough disk space. Free some space and try again." if error.errno == errno.ENOSPC else "Could not write the mix. Check disk permissions and try again.")
        except Exception:
            logger.exception("Audio job %s failed", job_id)
            self.fail(job_id, "Could not render the audio. Try again or shorten the mix.")

    def fail(self, job_id: str, message: str) -> None:
        with Session(self.database.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status, job.message = "error", message
            session.add(job)
            track = session.get(Track, job.track_id)
            if track and job.kind.startswith("import_"):
                track.status, track.error = "error", message
                session.add(track)
            session.commit()

    def run_import(self, job_id: str) -> None:
        last_update = 0.0
        last_message = ""

        def update(progress: float, message: str) -> None:
            nonlocal last_update, last_message
            now = time.monotonic()
            if message == last_message and now - last_update < 0.5:
                return
            with Session(self.database.engine) as session:
                job = session.get(Job, job_id)
                if job:
                    job.status, job.progress, job.message = "running", progress, message
                    session.add(job)
                    session.commit()
            last_update, last_message = now, message

        try:
            with Session(self.database.engine) as session:
                job = session.get(Job, job_id)
                track = session.get(Track, job.track_id) if job else None
                if track is None:
                    return
                session.expunge(track)
            if track.source_type == "youtube" and not self.database.original(track).is_file():
                from .importers.youtube import download_original

                download_original(self.database, track, update)
                with Session(self.database.engine) as session:
                    track = session.get(Track, track.id)
                    session.expunge(track)
            result = import_original(self.database, track, update)
            with Session(self.database.engine) as session:
                current = session.get(Track, track.id)
                job = session.get(Job, job_id)
                if not current or not job:
                    return
                tag_title = result.pop("tag_title")
                if tag_title and current.source_type != "youtube" and current.title == track.title:
                    current.title = str(tag_title).strip()[:300] or current.title
                for key, value in result.items():
                    setattr(current, key, value)
                current.status, current.error = "ready", None
                job.status, job.progress, job.message = "done", 1, "Ready"
                job.result_json = {**(job.result_json or {}), "track_id": track.id}
                session.add(current)
                session.add(job)
                session.commit()
        except AudioError as error:
            self.fail(job_id, str(error))
        except OSError as error:
            message = "Not enough disk space. Free some space and try again." if error.errno == errno.ENOSPC else "Could not access the audio files. Check disk permissions and try again."
            self.fail(job_id, message)
        except Exception:
            logger.exception("Import job %s failed", job_id)
            self.fail(job_id, "Import failed. Try again, or choose another copy of this song.")
