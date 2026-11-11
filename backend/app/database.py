from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from . import models  # Register the tables before create_all.


class Database:
    def __init__(self, directory: Path):
        self.directory = directory
        for name in ("originals", "work", "peaks", "exports", "previews"):
            (directory / name).mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{directory / 'app.db'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")

        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            if session.get(models.Project, models.DEFAULT_PROJECT_ID) is None:
                session.add(models.Project(id=models.DEFAULT_PROJECT_ID))
                session.commit()

    def original(self, track: models.Track) -> Path:
        return self.directory / "originals" / f"{track.id}{track.original_suffix}"

    def working(self, track_id: str) -> Path:
        return self.directory / "work" / f"{track_id}.wav"

    def peaks(self, track_id: str) -> Path:
        return self.directory / "peaks" / f"{track_id}.json"
