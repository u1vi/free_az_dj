"""Pure timeline arithmetic shared by project display and audio rendering."""

import math
from collections.abc import Mapping, Sequence


def timeline(clips: Sequence[Mapping]) -> dict:
    lengths = []
    for clip in clips:
        length = float(clip["end_s"]) - float(clip["start_s"])
        if not math.isfinite(length) or length <= 0:
            raise ValueError("Every clip must have a positive, finite length.")
        lengths.append(length)
    offsets = [0.0] if clips else []
    transitions, warnings = [], []
    for index in range(len(clips) - 1):
        kind = clips[index].get("transition", "crossfade")
        requested = float(clips[index].get("transition_s", 4))
        if not math.isfinite(requested) or requested < 0:
            raise ValueError("Transition lengths must be finite and nonnegative.")
        if kind == "crossfade":
            amount = min(requested, lengths[index] / 2, lengths[index + 1] / 2)
            if amount < requested - 0.000001:
                warnings.append(f"Crossfade after song {index + 1} was shortened to {amount:.3f} seconds.")
            offset = offsets[index] + lengths[index] - amount
        elif kind == "gap":
            amount = requested
            offset = offsets[index] + lengths[index] + amount
        elif kind == "cut":
            amount = 0.0
            offset = offsets[index] + lengths[index]
        else:
            raise ValueError("Choose crossfade, gap, or cut for each transition.")
        transitions.append(amount)
        offsets.append(offset)
    return {"lengths": lengths, "offsets": offsets, "transitions": transitions,
            "total": offsets[-1] + lengths[-1] if clips else 0.0, "warnings": warnings}


calculate_timeline = timeline
