import json
import math
import wave
from pathlib import Path

import numpy as np


def write_peaks(source: Path, destination: Path) -> None:
    """Read bounded chunks, including hour-long files, without loading the WAV."""
    peaks: list[float] = []
    with wave.open(str(source), "rb") as audio:
        channels, rate = audio.getnchannels(), audio.getframerate()
        duration = audio.getnframes() / rate
        bucket = max(1, math.floor(rate * 60 / 2000))
        while frames := audio.readframes(bucket * 256):
            samples = np.frombuffer(frames, dtype="<i2").astype(np.int32).reshape(-1, channels)
            amplitude = np.abs(samples).max(axis=1)
            values = np.maximum.reduceat(amplitude, np.arange(0, len(amplitude), bucket)) / 32768
            peaks.extend(values.tolist())
    temporary = destination.with_suffix(".part.json")
    temporary.write_text(json.dumps({"duration": duration, "peaks": peaks}, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)
