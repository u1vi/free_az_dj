"""ffmpeg rendering from immutable project snapshots; no browser audio processing."""

import copy
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .ffprobe import AudioError, probe
from .loudness import measure
from .timeline import timeline


def number(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def render_timeline(clips: Sequence[Mapping], settings: Mapping) -> dict:
    result = timeline(clips)
    # Preview transitions were already clamped against the full original clips.
    # Cropping playback windows must not shorten the transition a second time.
    override = settings.get("_preview_transition_s")
    if override is not None and len(clips) == 2:
        kind = clips[0].get("transition", "crossfade")
        amount = min(float(override), *result["lengths"]) if kind == "crossfade" else float(override)
        result["transitions"] = [amount]
        result["offsets"][1] = result["lengths"][0] + (amount if kind == "gap" else -amount if kind == "crossfade" else 0)
        result["total"] = result["offsets"][1] + result["lengths"][1]
    return result


def build_render_graph(clips: Sequence[Mapping], settings: Mapping) -> tuple[list[str], str]:
    """Return ffmpeg input arguments and a deterministic, side-effect-free graph."""
    if not clips:
        raise ValueError("Add at least one song to the mix before exporting.")
    timing = render_timeline(clips, settings)
    inputs, filters = [], []
    for index, clip in enumerate(clips):
        length = timing["lengths"][index]
        start = float(clip["start_s"])
        if not math.isfinite(start) or start < 0:
            raise ValueError("Clip starts must be finite and nonnegative.")
        inputs.extend(["-ss", number(start), "-t", number(length), "-i", str(clip["path"])])
        measured = clip.get("track_lufs")
        automatic = 0.0
        if settings.get("normalize", True) and measured is not None and math.isfinite(float(measured)):
            automatic = min(12.0, float(settings.get("target_lufs", -14)) - float(measured))
        gain = automatic + max(-12.0, min(12.0, float(clip.get("gain_db", 0))))
        previous_crossfade = index > 0 and clips[index - 1].get("transition", "crossfade") == "crossfade" and timing["transitions"][index - 1] > 0
        next_crossfade = index < len(clips) - 1 and clip.get("transition", "crossfade") == "crossfade" and timing["transitions"][index] > 0
        chain = [f"atrim=duration={number(length)}", "asetpts=PTS-STARTPTS", f"volume={number(gain)}dB"]
        fade_in = min(length, max(0.0, float(clip.get("fade_in_s", 0.5))))
        fade_out = min(length, max(0.0, float(clip.get("fade_out_s", 2))))
        if fade_in and not previous_crossfade:
            chain.append(f"afade=t=in:d={number(fade_in)}")
        if fade_out and not next_crossfade:
            chain.append(f"afade=t=out:st={number(length - fade_out)}:d={number(fade_out)}")
        chain.append("aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo")
        filters.append(f"[{index}:a]" + ",".join(chain) + f"[c{index}]")
    accumulator = "c0"
    for index in range(1, len(clips)):
        previous = clips[index - 1]
        duration = timing["transitions"][index - 1]
        kind = previous.get("transition", "crossfade")
        output = f"a{index}"
        if kind == "crossfade" and duration > 0:
            filters.append(f"[{accumulator}][c{index}]acrossfade=d={number(duration)}:c1=qsin:c2=qsin[{output}]")
        elif kind == "gap" and duration > 0:
            filters.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={number(duration)},asetpts=PTS-STARTPTS[g{index}]")
            filters.append(f"[{accumulator}][g{index}][c{index}]concat=n=3:v=0:a=1[{output}]")
        else:
            filters.append(f"[{accumulator}][c{index}]concat=n=2:v=0:a=1[{output}]")
        accumulator = output
    # Oversampling detects between-sample peaks. Leave headroom for MP3 encoding,
    # disable automatic make-up gain, and compensate the limiter's lookahead.
    correction = float(settings.get("_output_gain_db", 0))
    final = "aresample=192000,alimiter=limit=0.84:level=false:latency=true,aresample=44100"
    if correction:
        final += f",volume={number(correction)}dB"
    filters.append(f"[{accumulator}]{final}[out]")
    return inputs, ";\n".join(filters)


def ffmpeg_graph_option() -> str:
    output = subprocess.check_output(["ffmpeg", "-version"], text=True, encoding="utf-8", errors="replace")
    match = re.search(r"ffmpeg version n?(\d+)", output)
    return "-/filter_complex" if match and int(match.group(1)) >= 7 else "-filter_complex_script"


def render_audio(clips: Sequence[Mapping], settings: Mapping, destination: Path, options: Mapping,
                 progress: Callable[[float], None] = lambda _: None) -> dict:
    inputs, graph = build_render_graph(clips, settings)
    total = render_timeline(clips, settings)["total"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.part{destination.suffix}")
    try:
        with tempfile.TemporaryDirectory(prefix="graph-", dir=destination.parent) as graph_directory, tempfile.TemporaryFile() as errors:
            graph_path = Path(graph_directory) / "render.txt"
            graph_path.write_text(graph, encoding="utf-8")
            command = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-v", "error", "-filter_complex_threads", "1", *inputs,
                       ffmpeg_graph_option(), str(graph_path), "-map", "[out]", "-metadata", f"title={settings.get('name', 'Wedding mix')}",
                       "-ar", str(options.get("sample_rate", 44100)), "-ac", "2"]
            if options.get("format", "mp3") == "wav":
                command.extend(["-c:a", "pcm_s24le" if options.get("bit_depth", 16) == 24 else "pcm_s16le", "-rf64", "auto"])
            else:
                command.extend(["-c:a", "libmp3lame", "-b:a", f"{options.get('bitrate', 320)}k", "-id3v2_version", "3"])
            command.extend(["-progress", "pipe:1", "-nostats", str(temporary)])
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8", errors="replace")
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    key, _, value = line.strip().partition("=")
                    if key == "out_time_us":
                        try:
                            progress(max(0.0, min(1.0, float(value) / 1_000_000 / total)))
                        except ValueError:
                            pass
                if process.wait():
                    errors.seek(0, 2)
                    errors.seek(max(0, errors.tell() - 16_384))
                    message = errors.read().decode("utf-8", errors="replace").lower()
                    if "no space left on device" in message:
                        raise AudioError("Not enough disk space. Free some space and export again.")
                    raise AudioError("Could not render this mix. Check that every song is still available and try again.")
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        temporary.replace(destination)
        progress(1)
        return {"duration_s": probe(destination)["duration"]}
    except FileNotFoundError:
        raise AudioError("ffmpeg is missing. Install it and restart the app before exporting.") from None
    finally:
        temporary.unlink(missing_ok=True)


def safe_title(title: str) -> str:
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", str(title)).strip(" .")[:160] or "Song"


def tracklist_text(clips: Sequence[Mapping]) -> str:
    timing = timeline(clips)
    lines = []
    for offset, clip in zip(timing["offsets"], clips):
        seconds = max(0, math.floor(offset + 0.000001))
        title = str(clip.get("title", "Song")).replace("\r", " ").replace("\n", " ").replace("\x00", "")
        lines.append(f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}  {title}")
    return "\n".join(lines) + "\n"


def estimate_export_bytes(clips: Sequence[Mapping], options: Mapping) -> int:
    total = timeline(clips)["total"]
    if options.get("format", "mp3") == "wav":
        bytes_per_second = options.get("sample_rate", 44100) * 2 * options.get("bit_depth", 16) / 8
    else:
        bytes_per_second = options.get("bitrate", 320) * 1000 / 8
    if options.get("also_separate_files"):
        total += sum(float(clip["end_s"]) - float(clip["start_s"]) for clip in clips)
    # A second output may be needed to correct a lossy codec's true-peak overshoot.
    return math.ceil(total * bytes_per_second * 2.2) + 20 * 1024 * 1024


def execute_export(database, job_id: str, snapshot: dict, options: dict, update: Callable[[float, str], None]) -> dict:
    clips, settings = snapshot["clips"], snapshot["settings"]
    total = timeline(clips)["total"]
    folder = database.directory / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(folder).free < estimate_export_bytes(clips, options):
        raise AudioError("Not enough disk space for this export. Free some space and try again.")
    extension = options.get("format", "mp3")
    output = folder / f"{job_id}.{extension}"
    render_audio(clips, settings, output, options, lambda fraction: update(0.02 + fraction * 0.68, "Rendering mix"))
    update(0.71, "Checking output volume")
    loudness, peak = measure(output, total)
    # MP3 can create extra true peaks. Re-render from the original PCM sources,
    # rather than repeatedly transcoding the compressed result, if correction is needed.
    if peak is not None and peak > -1.05:
        corrected = {**settings, "_output_gain_db": -1.25 - peak}
        render_audio(clips, corrected, output, options, lambda fraction: update(0.72 + fraction * 0.09, "Adding peak headroom"))
        loudness, peak = measure(output, total)
        if peak is not None and peak > -1:
            raise AudioError("The encoded output exceeded the peak limit. Try WAV export for this mix.")
    (folder / f"{job_id}.txt").write_text(tracklist_text(clips), encoding="utf-8")
    result = {"export_id": job_id, "duration_s": total, "loudness_lufs": loudness, "true_peak_db": peak,
              "format": extension, "project_name": settings.get("name", "Wedding mix"),
              "mix_url": f"/api/exports/{job_id}/download?kind=mix",
              "tracklist_url": f"/api/exports/{job_id}/download?kind=tracklist"}
    if options.get("also_separate_files"):
        update(0.82, "Exporting individual songs")
        with tempfile.TemporaryDirectory(prefix="separate-", dir=folder) as temporary_directory:
            with zipfile.ZipFile(folder / f"{job_id}.zip", "w", compression=zipfile.ZIP_STORED) as archive:
                for index, clip in enumerate(clips):
                    path = Path(temporary_directory) / f"{index + 1:02d}.{extension}"
                    render_audio([clip], settings, path, options)
                    archive.write(path, f"{index + 1:02d} - {safe_title(clip.get('title', 'Song'))}.{extension}")
                    path.unlink()
                    update(0.82 + (index + 1) / len(clips) * 0.17, "Exporting individual songs")
        result["separate_url"] = f"/api/exports/{job_id}/download?kind=separate"
    update(1, "Export ready")
    return result


def preview_snapshot(snapshot: dict, clip_index: int) -> dict:
    original = snapshot["clips"]
    if not 0 <= clip_index < len(original) - 1:
        raise ValueError("Choose a transition between two songs.")
    first, second = copy.deepcopy(original[clip_index:clip_index + 2])
    full_timing = timeline(original)
    first_start = float(first["start_s"])
    first["start_s"] = max(first_start, float(first["end_s"]) - 12)
    if first["start_s"] > first_start or (clip_index > 0 and original[clip_index - 1].get("transition", "crossfade") == "crossfade" and full_timing["transitions"][clip_index - 1] > 0):
        first["fade_in_s"] = 0
    second_end = float(second["end_s"])
    second["end_s"] = min(second_end, float(second["start_s"]) + 12)
    if second["end_s"] < second_end or (clip_index + 2 < len(original) and second.get("transition", "crossfade") == "crossfade" and full_timing["transitions"][clip_index + 1] > 0):
        second["fade_out_s"] = 0
    settings = {**snapshot["settings"], "_preview_transition_s": full_timing["transitions"][clip_index]}
    return {"clips": [first, second], "settings": settings}


def execute_preview(database, job_id: str, snapshot: dict, clip_index: int, update: Callable[[float, str], None]) -> dict:
    cropped = preview_snapshot(snapshot, clip_index)
    output = database.directory / "previews" / f"{job_id}.mp3"
    output.parent.mkdir(parents=True, exist_ok=True)
    render_audio(cropped["clips"], cropped["settings"], output, {"format": "mp3", "bitrate": 128}, lambda fraction: update(fraction, "Preparing transition preview"))
    return {"export_id": job_id, "duration_s": render_timeline(cropped["clips"], cropped["settings"])["total"],
            "preview_url": f"/api/exports/{job_id}/download?kind=preview"}


def execute_mix_preview(database, job_id: str, snapshot: dict, update: Callable[[float, str], None]) -> dict:
    """Render the whole mix with the export graph, as a light MP3 for listening before export."""
    clips, settings = snapshot["clips"], snapshot["settings"]
    options = {"format": "mp3", "bitrate": 128}
    output = database.directory / "previews" / f"{job_id}.mp3"
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < estimate_export_bytes(clips, options):
        raise AudioError("Not enough disk space to prepare the preview. Free some space and try again.")
    render_audio(clips, settings, output, options, lambda fraction: update(fraction, "Preparing full mix preview"))
    timing = timeline(clips)
    return {"export_id": job_id, "duration_s": timing["total"], "full_mix": True,
            "preview_url": f"/api/exports/{job_id}/download?kind=preview",
            "songs": [{"title": str(clip.get("title", "Song")), "start_s": offset} for clip, offset in zip(clips, timing["offsets"])]}
