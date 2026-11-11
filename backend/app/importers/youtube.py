"""YouTube URLs, metadata, downloads, and messages shared by the import API."""

import errno
import math
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from sqlmodel import Session
from yt_dlp import YoutubeDL

from ..audio.ffprobe import AudioError
from ..database import Database
from ..models import Job, Track

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
PLAYLIST_ID = re.compile(r"[A-Za-z0-9_-]{10,200}\Z")
DOWNLOAD_SLOTS = threading.BoundedSemaphore(2)
LONG_VIDEO_WARNING = "This video is longer than 20 minutes. Check that it is the song you want."
UPDATE_COMMAND = "python -m pip install -U 'yt-dlp[default]'"


@dataclass(frozen=True)
class YouTubeURL:
    url: str
    video_id: str | None = None
    playlist_id: str | None = None

    @property
    def is_playlist(self) -> bool:
        return self.video_id is None and self.playlist_id is not None


def parse_url(value: str) -> YouTubeURL:
    """Only canonical YouTube video/playlist URLs can reach yt-dlp."""
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            raise ValueError
        host = (parsed.hostname or "").lower()
        if host not in ("youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"):
            raise ValueError
        query = parse_qs(parsed.query)
        path = parsed.path.rstrip("/")
        video = None
        playlist = query.get("list", [None])[0]
        if host.endswith("youtu.be"):
            video = path.lstrip("/")
        elif path == "/watch":
            video = query.get("v", [None])[0]
        elif path.startswith("/shorts/"):
            video = path.removeprefix("/shorts/")
        elif path != "/playlist":
            raise ValueError
        if video:
            if not VIDEO_ID.fullmatch(video):
                raise ValueError
            # A watch link with list= still means this one video.
            return YouTubeURL(f"https://www.youtube.com/watch?{urlencode({'v': video})}", video_id=video)
        if playlist and PLAYLIST_ID.fullmatch(playlist):
            return YouTubeURL(f"https://www.youtube.com/playlist?{urlencode({'list': playlist})}", playlist_id=playlist)
        raise ValueError
    except (ValueError, AttributeError):
        raise AudioError("Paste a valid YouTube video or playlist link.") from None


def error_message(error: BaseException | str) -> str:
    message = str(error).lower()
    if any(part in message for part in ("not available in your country", "not available in your region", "not made this video available", "not available from your location", "geo-restricted", "region blocked", "geographic restriction")):
        return "This video is blocked in your region. Choose another YouTube link."
    if any(part in message for part in ("age-restricted", "age restricted", "confirm your age", "inappropriate for some users")):
        return "This video is age-restricted. Choose another video or import a local audio file."
    if any(part in message for part in ("private video", "video is private", "video unavailable", "video is unavailable", "is not available", "has been removed", "video does not exist", "members-only", "this playlist does not exist", "playlist is private", "http error 404")):
        return "This video or playlist is unavailable or private. Choose another YouTube link."
    if any(part in message for part in ("confirm you’re not a bot", "confirm you're not a bot", "sign in to confirm you", "login required", "cookies are needed")):
        return "YouTube is asking for a browser sign-in. Try again later or import a local audio file."
    if "http error 429" in message or "too many requests" in message:
        return "YouTube is limiting downloads. Wait a few minutes and try again."
    if "javascript runtime" in message and any(part in message for part in ("not found", "could be found", "missing", "required")):
        return "Deno is missing or could not run. Install Deno and restart the app."
    if isinstance(error, (ConnectionError, TimeoutError)) or any(part in message for part in ("timed out", "timeout", "temporary failure in name resolution", "name or service not known", "network is unreachable", "connection refused", "connection reset", "unable to download webpage", "http error 502", "http error 503")):
        return "Could not connect to YouTube. Check your internet connection and try again."
    return f"YouTube changed something. Update yt-dlp, then retry: {UPDATE_COMMAND}"


class QuietLogger:
    # Errors are raised by yt-dlp and mapped above, rather than printed as jargon.
    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def options() -> dict:
    return {
        "format": "bestaudio/best", "noplaylist": True, "quiet": True,
        "no_warnings": True, "logger": QuietLogger(), "cachedir": False,
        "socket_timeout": 15, "retries": 2, "extractor_retries": 2,
        "js_runtimes": {"deno": {}},
    }


def duration(value) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def playlist_entries(url: str) -> list[dict]:
    parsed = parse_url(url)
    if not parsed.is_playlist:
        raise AudioError("Paste a YouTube playlist link to choose its songs.")
    settings = {**options(), "noplaylist": False, "extract_flat": "in_playlist", "skip_download": True, "ignoreerrors": True}
    try:
        with YoutubeDL(settings) as downloader:
            info = downloader.extract_info(parsed.url, download=False)
            raw_entries = list(info.get("entries") or []) if info else []
        if not info:
            raise AudioError("This playlist is unavailable or private. Choose another YouTube link.")
        result = []
        seen: set[str] = set()
        for entry in raw_entries:
            if not entry:
                continue
            identifier = str(entry.get("id") or "")
            if not VIDEO_ID.fullmatch(identifier):
                try:
                    identifier = parse_url(str(entry.get("url") or "")).video_id or ""
                except AudioError:
                    continue
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            result.append({"url": f"https://www.youtube.com/watch?v={identifier}",
                           "title": str(entry.get("title") or "YouTube video")[:300],
                           "duration_s": duration(entry.get("duration"))})
        if not result:
            raise AudioError("This playlist has no available videos. Choose another playlist.")
        return result
    except AudioError:
        raise
    except Exception as error:
        raise AudioError(error_message(error)) from None


def downloaded_file(database: Database, track: Track, info: dict, downloader) -> Path:
    originals = (database.directory / "originals").resolve()
    candidates = [item.get("filepath") for item in info.get("requested_downloads") or [] if isinstance(item, dict)]
    candidates.extend([info.get("filepath"), info.get("_filename"), downloader.prepare_filename(info)])
    candidates.extend(originals.glob(f"{track.id}.*"))
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve()
        if path.parent != originals or not path.name.startswith(track.id + "."):
            continue
        if path.suffix.lower() in (".part", ".ytdl", ".tmp", ".temp", ".pending", ".json"):
            continue
        if re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", path.suffix) and path.is_file():
            return path
    raise AudioError("YouTube download did not finish. Check your connection and retry.")


def download_original(database: Database, track: Track, update: Callable[[float, str], None]) -> None:
    """Download into UUID paths and persist the actual extension for the pipeline."""
    parsed = parse_url(track.source_url or "")
    if parsed.is_playlist:
        raise AudioError("Choose individual songs from the playlist first.")
    update(0, "Waiting for YouTube download")

    def progress(event: dict) -> None:
        if event.get("status") == "downloading":
            total = duration(event.get("total_bytes") or event.get("total_bytes_estimate"))
            complete = duration(event.get("downloaded_bytes")) or 0
            fraction = min(1, complete / total) if total else 0
            update(fraction * 0.08, "Downloading audio")
        elif event.get("status") == "finished":
            update(0.08, "YouTube download complete")

    settings = {**options(), "outtmpl": str(database.directory / "originals" / f"{track.id}.%(ext)s"),
                "progress_hooks": [progress], "overwrites": False, "continuedl": True}
    try:
        with DOWNLOAD_SLOTS, YoutubeDL(settings) as downloader:
            update(0, "Downloading audio")
            info = downloader.extract_info(parsed.url, download=True)
            if not info:
                raise AudioError("This video is unavailable or private. Choose another YouTube link.")
            path = downloaded_file(database, track, info, downloader)
        title = str(info.get("title") or "YouTube video").strip()[:300] or "YouTube video"
        with Session(database.engine) as session:
            current = session.get(Track, track.id)
            if current is None:
                raise AudioError("This song was removed before the download finished.")
            if current.title == track.title:
                current.title = title
            current.original_suffix = path.suffix
            current.original_name = (title + path.suffix)[:1000]
            current.source_url = parsed.url
            session.add(current)
            seconds = duration(info.get("duration"))
            if seconds is not None and seconds > 1200 and current.job_id:
                job = session.get(Job, current.job_id)
                if job:
                    job.result_json = {**(job.result_json or {}), "warning": LONG_VIDEO_WARNING}
                    session.add(job)
            session.commit()
    except AudioError:
        raise
    except OSError as error:
        # Preserve filesystem errors for the runner, but map network OSErrors here.
        if error.errno in (errno.ENOSPC, errno.EACCES, errno.EPERM, errno.EROFS, errno.EDQUOT):
            raise
        raise AudioError(error_message(error)) from None
    except Exception as error:
        raise AudioError(error_message(error)) from None
