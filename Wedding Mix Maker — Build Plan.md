# Wedding Mix Maker — Build Plan

Oct 29, 2026

## Goal and scope

Build a small local web app with four steps: import songs (any audio/video file or a YouTube link), trim each one, put them in order with smooth transitions, and export one WAV or MP3 mix.

It is for a family wedding in a rural district where no DJ is available. Mixxx was too complex. This app should be simpler than any DJ software. The user is technical, but the UI must work for a non-technical relative too.

**Success criteria**

- Import 30+ songs from mixed sources (MP3, M4A, FLAC, WAV, OGG, OPUS, MP4/MKV video, YouTube links) with no manual conversion.
- Set start and end points precisely (within 50 ms) using a waveform and playback.
- Export a 1–2 hour mix with crossfades, similar loudness across songs, and no clipping.
- Runs on one laptop with a single command. No account. Internet is needed only for YouTube import.

**Out of scope — do not build:** user accounts, cloud hosting, BPM detection or beat sync, EQ or effects beyond gain and fades, live DJ playback, mobile layout, multi-user editing, a database server.

## Architecture and stack

Run it as a local app on the laptop at `http://localhost:8000`, not on a hosted server. YouTube often blocks downloads from cloud and datacenter IPs, large audio files never have to cross the internet, and there is nothing to host or pay for.

One Python process serves both the API and the built React app. ffmpeg does all decoding, analysis and rendering. yt-dlp fetches YouTube audio.

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn | Simple, async, streams files with HTTP Range support |
| Audio engine | ffmpeg 6+ and ffprobe (system binaries) | Decodes almost any format; one filter graph does trims, fades, crossfades, loudness |
| YouTube | `yt-dlp` Python package, plus Deno | Since yt-dlp 2025.11.12 an external JavaScript runtime is needed for full YouTube support; Deno is the recommended one ([yt-dlp #15012](https://github.com/yt-dlp/yt-dlp/issues/15012)). Node 20+ is a supported fallback but must be enabled explicitly — check the yt-dlp README for the current option name |
| Storage | SQLite (via SQLModel) plus audio files in `./data` | No database server |
| Background jobs | In-process `ThreadPoolExecutor` plus a `jobs` table; frontend polls every second | No Redis or Celery |
| Frontend | React, TypeScript, Vite | Fast to build |
| Waveform | wavesurfer.js v7 with the Regions, Timeline and Zoom plugins | Draggable trim region over the waveform |
| Reordering | dnd-kit | Drag-and-drop list |
| Styling | Tailwind CSS | No custom design system needed |

**Run modes:** `make dev` runs Vite and Uvicorn with hot reload. `make run` builds the frontend into `backend/static/` and starts one Uvicorn process that opens the browser. Add an optional `Dockerfile` that bundles ffmpeg and Deno.

**Repo layout**

```
wedding-mix/
  backend/
    app/
      main.py          # FastAPI app, static files
      api/             # routers: tracks.py, projects.py, jobs.py, exports.py
      audio/           # ffprobe.py, transcode.py, peaks.py, loudness.py, render.py, timeline.py
      importers/       # upload.py, youtube.py
      models.py        # SQLModel tables
      jobs.py          # job runner + progress
      settings.py
    tests/
    pyproject.toml
  frontend/
    src/
      components/      # Library, ClipEditor, Timeline, ExportDialog, ImportBar
      api/             # typed client
      store/           # Zustand store
    package.json
  data/                # gitignored: originals/, work/, peaks/, exports/, app.db
  Makefile
  README.md
```

&#91;embedded content: request flow · import, edit, render\]

Uploads and YouTube links meet in one import job. The browser edits the project through the API, and Export hands it to the ffmpeg render job.

## Data model and storage

Keep **Track** (an imported song) separate from **Clip** (one trimmed use of a track in the mix). The same song can then appear twice with different cuts, and deleting a clip never deletes the audio.

**Track** — one per imported file or YouTube video

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Also the file name on disk |
| `title` | str | From tags, YouTube title, or file name; user can rename |
| `source_type` | `upload` \| `youtube` |  |
| `source_url` | str? | YouTube URL |
| `original_name` | str? | Uploaded file name, kept for display only |
| `duration_s` | float | From ffprobe on the working file |
| `loudness_lufs` | float | Integrated loudness, measured at import |
| `true_peak_db` | float | Measured at import |
| `status` | `importing` \| `ready` \| `error` |  |
| `error` | str? | Human-readable message |
| `created_at` | datetime |  |

**Project** — one mix. The MVP needs only one, but store an id so multiple mixes are easy later (e.g. "Ceremony" and "Dance floor").

| Field | Type | Notes |
| --- | --- | --- |
| `id`, `name` |  |  |
| `default_crossfade_s` | float | Default 4.0 |
| `normalize` | bool | Default true |
| `target_lufs` | float | Default −14 |
| `updated_at` | datetime |  |

**Clip** — ordered items in a project

| Field | Type | Notes |
| --- | --- | --- |
| `id`, `project_id`, `track_id` | UUID |  |
| `position` | int | Order in the mix |
| `start_s`, `end_s` | float | Trim points within the track; `0 ≤ start < end ≤ duration` |
| `fade_in_s`, `fade_out_s` | float | Default 0.5 / 2.0 |
| `gain_db` | float | User adjustment on top of normalization, −12 to +12 |
| `transition` | `crossfade` \| `gap` \| `cut` | How this clip goes into the NEXT one |
| `transition_s` | float | Crossfade length or silence length |

**Job** — `id`, `kind` (`import_upload`, `import_youtube`, `export`, `preview`), `status` (`queued`, `running`, `done`, `error`), `progress` 0–1, `message`, `result_json`.

**Files on disk**

- `data/originals/<track_id>.<ext>` — untouched source, kept for re-processing.
- `data/work/<track_id>.wav` — working copy: 44.1 kHz, stereo, 16-bit PCM. All editing and rendering reads this.
- `data/peaks/<track_id>.json` — precomputed waveform peaks (\~2,000 points per minute) so long songs draw instantly.
- `data/exports/<export_id>.(mp3|wav|zip)` plus a `.txt` tracklist.
- Never use user-supplied names as paths. Azerbaijani and Cyrillic titles (ə, ğ, ş, ж) stay in the database only.

## Backend: import, jobs, API

Every import ends in the same state: a working WAV, a peaks file, measured loudness, and a Track with status `ready`. Uploads and YouTube links differ only in how the original file arrives.

**Import pipeline (shared, runs as a background job)**

1. Save the original to `data/originals/`.
2. `ffprobe` it. Reject if there is no audio stream ("This file has no audio").
3. Transcode to the working WAV: `ffmpeg -i <orig> -vn -map 0:a:0 -ac 2 -ar 44100 -c:a pcm_s16le data/work/<id>.wav`. This handles mono, odd sample rates, and video files.
4. Measure loudness: run `loudnorm=print_format=json` (analysis only, output to `-f null -`) and store `input_i` and `input_tp`.
5. Compute peaks with numpy from the working WAV (max absolute value per bucket, both channels merged, normalized 0–1). Write JSON `{duration, peaks: [...]}`.
6. Detect leading and trailing silence with `silencedetect=n=-45dB:d=0.5`. Use it only to suggest default trim points for new clips, never to cut the track itself.
7. Set status `ready`. On any failure set `error` with a readable message and keep the original for retry.

Report progress per step (0.1, 0.5, 0.7, 0.9, 1.0). Parse ffmpeg progress from `-progress pipe:1` for the transcode step.

**YouTube import**

- Accept `youtube.com/watch`, `youtu.be`, `music.youtube.com`, and `youtube.com/shorts` links. Strip tracking parameters.
- Use the yt-dlp Python API with `format: "bestaudio/best"`, `noplaylist: True`, and a progress hook that writes to the job. Download to `data/originals/`, then run the shared pipeline.
- Playlist links: return the list of entries (title, duration) and let the user tick which to import. Each becomes its own job.
- Use the video title as the track title. Warn (do not block) for videos longer than 20 minutes, since those are usually full concerts or compilations.
- Map common errors to plain messages: unavailable or private video, age-restricted, region-blocked, network down, and "YouTube changed something — update yt-dlp" with the exact command.
- Add a `GET /api/system/check` endpoint that reports ffmpeg, ffprobe, yt-dlp and Deno versions. Show warnings in the UI if any are missing.
- Run at most 2 YouTube downloads at a time.

**API endpoints**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/system/check` | Tool versions and missing dependencies |
| POST | `/api/tracks/upload` | Multipart, many files at once; returns one job per file |
| POST | `/api/tracks/{id}/retry` | Retry a failed import from its saved original |
| POST | `/api/tracks/youtube` | `{url}` → job, or `{playlist: [...]}` for the user to choose from |
| GET | `/api/tracks` | Library list with each track's latest job and progress |
| PATCH | `/api/tracks/{id}` | Rename |
| DELETE | `/api/tracks/{id}` | Refuse with 409 if a clip uses it, unless `?force=true` |
| GET | `/api/tracks/{id}/audio` | Working WAV, must support HTTP Range for seeking |
| GET | `/api/tracks/{id}/peaks` | Peaks JSON |
| GET | `/api/projects/{id}` | Project with ordered clips |
| PUT | `/api/projects/{id}` | Save settings and the full clip list (autosave target) |
| POST | `/api/projects/{id}/clips` | Add a track to the end of the mix, with suggested trims |
| POST | `/api/projects/{id}/preview-transition` | `{clip_index}` → job rendering the last 12 s of clip *i* and the first 12 s of clip *i+1* with the real transition |
| POST | `/api/projects/{id}/export` | `{format, bitrate, sample_rate, also_separate_files}` → job |
| GET | `/api/jobs/{id}` | Status, progress, message, result |
| GET | `/api/exports/{id}/download` | The finished file |

Validate all clip fields on the server with Pydantic and clamp impossible values (for example, a crossfade longer than either neighbouring clip).

## Audio engine: timeline, render, export

The whole mix is rendered by one ffmpeg command built from a pure Python function, `build_render_graph(clips, settings) -> (inputs, filter_graph)`. Keep this function free of I/O so it is easy to unit-test.

**Timeline math** (`audio/timeline.py`, also mirrored in the frontend for display)

- `len[i] = end_s[i] − start_s[i]`
- `offset[0] = 0`
- `offset[i+1] = offset[i] + len[i] − X[i]` for a crossfade of `X[i]` seconds; `+ G[i]` for a gap of `G[i]` seconds; `+ 0` for a hard cut
- `total = offset[last] + len[last]`
- Clamp every crossfade to `min(X, 0.5 × len[i], 0.5 × len[i+1])` and warn in the UI when clamped.

**Per-clip chain**

- Input each working WAV with `-ss start_s -t len` (sample-accurate for PCM).
- Gain: `volume=<V>dB` where `V = (target_lufs − track_lufs) + gain_db` when normalization is on, else `gain_db`. Cap the automatic boost at +12 dB.
- Fades: apply the clip's own `fade_in` only if the previous transition is not a crossfade, and its `fade_out` only if the next transition is not a crossfade. Crossfades bring their own curves.
- Convert to float internally: `aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo`.

**Joining** — fold left over the clips:

- Crossfade: `[acc][ci]acrossfade=d=X:c1=qsin:c2=qsin[acc2]` (equal-power, no volume dip in the middle).
- Cut: `[acc][ci]concat=n=2:v=0:a=1[acc2]`.
- Gap: generate silence with `anullsrc=r=44100:cl=stereo,atrim=duration=G`, then concat `acc`, silence, `ci`.
- Final stage: `alimiter=limit=0.89:level=false` (about −1 dBFS) so normalization never clips.

Example graph for three clips (crossfade 4 s, then a hard cut):

```
[0:a]volume=-2.1dB,afade=t=in:d=0.5,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[c0];
[1:a]volume=1.4dB,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[c1];
[2:a]volume=0.0dB,afade=t=out:st=178:d=2,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[c2];
[c0][c1]acrossfade=d=4:c1=qsin:c2=qsin[a1];
[a1][c2]concat=n=2:v=0:a=1[a2];
[a2]alimiter=limit=0.89:level=false[out]
```

Write the graph to a file instead of the command line (30+ clips get long): `-/filter_complex graph.txt` on ffmpeg 7+, `-filter_complex_script graph.txt` on ffmpeg 6. Detect the version at startup.

Progress = ffmpeg's `out_time_ms` from `-progress pipe:1` divided by the computed total.

**Export formats**

| Option | ffmpeg output |
| --- | --- |
| MP3 (default) | `-c:a libmp3lame -b:a 320k` (offer 192 / 256 / 320), 44.1 kHz, ID3 title = project name |
| WAV | `-c:a pcm_s16le -ar 44100` (offer 24-bit / 48 kHz as an advanced option) |
| Separate files (checkbox) | Each clip rendered alone with its gain and fades, named `01 - Title.mp3`, zipped. A backup if the person playing music needs to skip a song at the wedding |

Every export also writes `tracklist.txt` with the start time of each song (`00:14:32  Title`), so whoever runs the music knows where each song begins. After rendering, measure the output's loudness and true peak and include them in the job result as a sanity check.

**Transition preview** uses the same builder on two clips trimmed to their last and first 12 seconds, encoded as 128 kbps MP3 into `data/previews/`. It should finish in under 2 seconds.

## Frontend: one screen, three panels

Everything happens on a single page: **Library** on the left, **Clip editor** in the centre, **Mix list** along the bottom, and an **Export** button top right. No routing is needed.

Importing remains available while trimming and arranging. Keep **Add music**
and the Library import controls accessible throughout the workspace; these are
tasks, not locked wizard stages. Adding more files or YouTube links must preserve
existing trim edits and mix order. New imports appear in the Library and can be
added to the mix once they are ready.

**Import bar (top of Library)**

- A drop zone that accepts many files at once, plus a "Choose files" button.
- A text field: "Paste a YouTube link" with an Add button. Pressing Enter also submits. Pasting a playlist link opens a checklist dialog.
- Each importing track shows a row with a progress bar and its current step (Downloading, Converting, Analysing). Errors show the message and a Retry button.

**Library**

- Rows: title (click to rename), duration, source icon (file or YouTube), and an "Add to mix" button. Double-click also adds.
- A search box filters by title.
- A small play button previews the original song.

**Clip editor (selected clip)**

- wavesurfer.js waveform drawn from the precomputed peaks, with zoom (mouse wheel and a slider) and a time ruler.
- One draggable region marks start and end. Everything outside it is dimmed.
- Start and end fields in `mm:ss.mmm`, editable by typing, kept in sync with the region.
- Nudge buttons for start and end: −1 s, −0.1 s, +0.1 s, +1 s.
- Buttons: Play selection, Play the first 5 s, Play the last 5 s (the most common check when trimming).
- Fade-in and fade-out sliders (0–10 s), a gain slider (−12 to +12 dB) with a Reset link.
- A "Trim silence" button that applies the suggested trims from import.
- Show the clip length and a quiet loudness readout ("−16 LUFS, will be raised 2 dB").

**Mix list (bottom)**

- Horizontal or vertical list of clip cards in play order, dragged to reorder with dnd-kit. Each card shows the number, title, trimmed length, and start time in the mix.
- Between every two cards, a small transition control: Crossfade / Gap / Cut, with a seconds field, and a ▶ button that renders and plays the transition preview.
- Card actions: Duplicate, Remove. Clicking a card opens it in the editor.
- Footer: total mix length, number of songs, project default crossfade.

**Export dialog**

- Format (MP3 or WAV), MP3 bitrate, "Even out volume between songs" checkbox (on by default), "Also export each song separately" checkbox.
- A progress bar while rendering, then a Download button for the mix, the zip (if chosen) and the tracklist.

**Keyboard shortcuts** (show them in a ? help popover)

| Key | Action |
| --- | --- |
| Space | Play / pause |
| I | Set start at playhead |
| O | Set end at playhead |
| ← / → | Move playhead 1 s (Shift: 0.1 s) |
| P | Play selection |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo clip edits |
| Delete | Remove selected clip from the mix |

**State and saving**

- Keep the project in a Zustand store. Autosave with `PUT /api/projects/{id}` 800 ms after the last change, and show "Saved" or "Saving…" in the header.
- Undo/redo keeps the last 50 project states in memory.
- Show times as `m:ss` in lists and `mm:ss.mmm` in the editor.

Keep the UI text in English, but put all strings in one `strings.ts` file so an Azerbaijani version is a simple swap later.

## Milestones

Build in this order. Each milestone must pass its checks before the next one starts. Milestones 1–5 are the usable MVP; 6 is polish.

1. **Skeleton.** Repo layout, FastAPI with `/api/system/check`, Vite React app calling it, Makefile, README with install steps.
   - Done when: `make dev` shows a page listing ffmpeg, yt-dlp and Deno versions, with a red warning for anything missing.
2. **File import and library.** Upload endpoint, shared import pipeline, jobs, library panel with progress.
   - Done when: dropping an MP3, an M4A, a FLAC, a mono WAV and an MP4 video at once gives five `ready` tracks with correct durations (±0.05 s), and a corrupt file shows a readable error.
3. **YouTube import.** yt-dlp integration, playlist chooser, error mapping.
   - Done when: a normal link, a `youtu.be` link and a 3-video playlist import correctly, and a private-video link shows a clear message without crashing the job runner.
4. **Clip editor and mix list.** Waveform with peaks, trim region, numeric fields, nudges, fades, gain, drag reordering, transition controls, autosave, undo.
   - Done when: a page reload restores the exact mix, and start/end set with the I and O keys match the waveform position within 50 ms.
5. **Render and export.** `build_render_graph`, transition preview, MP3/WAV export, tracklist, download.
   - Done when: a 3-clip mix with known trims exports with duration equal to the computed total (±0.05 s), true peak ≤ −1 dBTP, and the transition preview plays within 2 s.
6. **Polish.** Separate-files zip, silence trim suggestions, keyboard help, loudness readout, Dockerfile, clamping warnings.
   - Done when: a 30-song, 90-minute mix exports on an ordinary laptop in under 5 minutes, and a non-technical person can build a 3-song mix without help.

## Testing, edge cases and setup

**Tests (pytest)** — generate all fixtures with ffmpeg's `lavfi` sine and noise sources so no music files go in the repo.

- `timeline.py`: offsets and totals for crossfade, gap and cut mixes; clamping of oversized crossfades.
- `build_render_graph`: snapshot tests of the graph text for 1, 2 and 5 clips, and for every transition type.
- Integration: import a 1 kHz tone as MP3, a 440 Hz tone as OGG and a mono 22.05 kHz WAV; trim, mix, export; assert duration with ffprobe and true peak with `loudnorm` analysis.
- Normalization: two tones 10 dB apart come out within 1 LU of each other after export.
- YouTube: unit-test URL parsing and error mapping with a mocked yt-dlp. Mark one real-download test `@pytest.mark.network`, skipped by default.
- Frontend: Vitest for time formatting and the mirrored timeline math; one Playwright smoke test (import a generated file, add to mix, export, download exists).

**Edge cases to handle**

- Unicode and spaces in file names and titles (Azerbaijani ə ğ ı ş ç ö ü, Cyrillic).
- Files with several audio streams (use the first), video-only files (reject), very short clips (< 1 s), very long sources (1 h+).
- A clip whose end exceeds the track duration after a re-import: clamp and warn.
- Deleting a track used in the mix (409 unless forced; forced removes its clips).
- Export with zero clips: disable the button.
- Disk space: before export, check free space against the estimated output size (WAV about 10 MB per minute) and refuse with a clear message.
- Closing the tab mid-export: the job keeps running; reopening shows its progress.

**Setup (README)**

- Python 3.11+, Node 20+, ffmpeg 6+ on PATH, Deno on PATH.
- Windows: `winget install Gyan.FFmpeg` and `winget install DenoLand.Deno`. macOS: `brew install ffmpeg deno`. Ubuntu: `apt install ffmpeg`, then Deno's install script.
- `make setup` (creates venv, installs pip and npm packages), then `make run`.
- Document `pip install -U yt-dlp` as the first fix for YouTube errors; YouTube changes often and old yt-dlp versions break.

**Notes for Codex**

- Follow the milestones in order and stop for review after each one.
- Do not add features outside the scope list in the first section. When unsure, choose the simpler option and leave a `TODO` with the alternative.
- No audio processing in the browser except playback and waveform display; all rendering goes through ffmpeg on the backend.
- Run ffmpeg and yt-dlp with argument lists (`subprocess.run([...])`), never a shell string, because titles and URLs come from users.
- Bind the server to `127.0.0.1` only.

**Usage note:** downloading from YouTube may go against YouTube's terms of service. Keep this as a personal tool and use it with songs you have the right to play.

## Sources

- [yt-dlp announcement: external JavaScript runtime now required for full YouTube support (#15012)](https://github.com/yt-dlp/yt-dlp/issues/15012)
- [wavesurfer.js v7 (Regions, Timeline and other plugins)](https://github.com/katspaugh/wavesurfer.js/releases/tag/7.0.0)
