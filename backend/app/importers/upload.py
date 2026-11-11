"""One shared analysis pipeline; YouTube import can call this in milestone 3."""

from collections.abc import Callable

from ..audio.ffprobe import probe
from ..audio.loudness import measure, suggest_trims
from ..audio.peaks import write_peaks
from ..audio.transcode import transcode
from ..database import Database
from ..models import Track


def import_original(database: Database, track: Track, update: Callable[[float, str], None]) -> dict:
    original = database.original(track)
    working = database.working(track.id)
    update(0.1, "Reading audio")
    source = probe(original)
    update(0.1, "Converting audio")
    transcode(original, working, source["duration"], lambda fraction: update(0.1 + 0.4 * fraction, "Converting audio"))
    duration = probe(working)["duration"]
    update(0.5, "Analysing volume")
    loudness, peak = measure(working, duration)
    update(0.7, "Preparing waveform")
    write_peaks(working, database.peaks(track.id))
    update(0.9, "Checking silence")
    start, end = suggest_trims(working, duration)
    return {"duration_s": duration, "loudness_lufs": loudness, "true_peak_db": peak,
            "suggested_start_s": start, "suggested_end_s": end, "tag_title": source["title"]}
