# Wedding Mix Maker

**English** · [Azərbaycanca](README.az.md)

> Hiring a DJ is expensive. Wedding Mix Maker is a simple app for making your
> own DJ set: add songs or YouTube links, trim them, set smooth transitions,
> and export one mix that is ready to play.

A small local web app for preparing wedding music on one laptop, without a DJ
or DJ software. Import songs, trim them on a waveform, arrange transitions, and
export one WAV or MP3 mix. No account, no hosting, no cloud. Your music stays
on your machine.

It was built for a family wedding in a rural area where no DJ was available.
DJ programs were too complex, so the interface is designed to be usable by a
non-technical relative.

## Features

- **Import from anywhere.** Drop in audio or video files (MP3, M4A, FLAC, WAV,
  OGG, OPUS, MP4, MKV, and anything else ffmpeg can decode) or paste YouTube
  video and playlist links. For playlists, choose which songs to add.
- **Library.** Background import jobs with progress, search, rename, preview
  playback, remove, and retry for failed imports. Jobs survive closing the tab.
- **Trim precisely.** Set start and end points on a zoomable waveform, with
  keyboard shortcuts (`i` / `o` to set start and end at the playhead) and
  automatic silence-trim suggestions.
- **Arrange the mix.** Drag-and-drop ordering, per-song fades and gain, and a
  crossfade, gap, or hard cut between each pair of songs. Preview any single
  transition. Undo and redo.
- **Even loudness.** Optional loudness normalization to a target LUFS level so
  songs play at a similar volume, without clipping.
- **Listen before exporting.** Render the full mix as a light preview using the
  same audio graph as the export, and jump to any song.
- **Export.** One MP3 (192/256/320 kbps) or WAV file, a tracklist, and
  optionally a ZIP of the individual songs.
- Titles may contain Azerbaijani, Cyrillic, or any other Unicode characters.

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLite via SQLModel |
| Audio | ffmpeg / ffprobe (decoding, analysis, rendering) |
| YouTube | yt-dlp with Deno as its JavaScript runtime |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Zustand |
| Waveform and ordering | wavesurfer.js, dnd-kit |
| Tests | pytest, Vitest, Playwright |

One Python process serves the API and the built React app. All audio
processing happens on the backend; the browser only uploads and plays audio.

## Quick start with Docker

Requires Docker with the Compose plugin.

```sh
docker compose up --build -d --wait
```

Open **http://127.0.0.1:8000**. The image includes Python, ffmpeg, yt-dlp,
Deno, and the built frontend, so nothing else needs to be installed on the host.
The first build needs internet access.

- The port is published on `127.0.0.1` only, so the app is not reachable from
  your network.
- Use another host port if 8000 is taken:
  `WEDDING_MIX_PORT=8001 docker compose up --build -d --wait`
  (PowerShell: `$env:WEDDING_MIX_PORT = "8001"` first).
- Logs: `docker compose logs -f app`. Stop: `docker compose down`.
- Data is kept in the named `mix-data` volume. `docker compose down --volumes`
  **deletes your Library**; avoid it unless that is what you want.
- To update yt-dlp after YouTube changes, rebuild:
  `docker compose build --no-cache --pull && docker compose up -d --wait`

`make docker-run` and `make docker-stop` are shortcuts.

## Running natively

### Requirements

- Python 3.11+ (with `venv` and pip) or [uv](https://docs.astral.sh/uv/)
- Node.js 22.12+ or 20.19+ with npm
- ffmpeg **6 or newer**, including ffprobe, on `PATH`
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) on `PATH` (YouTube import only)
- GNU Make (on Windows, use WSL or the commands below)

Install the system tools:

```sh
# macOS
brew install python node ffmpeg deno

# Ubuntu (check `ffmpeg -version`; some releases ship ffmpeg older than 6)
sudo apt install python3 python3-venv python3-pip ffmpeg make
```

```powershell
# Windows
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
winget install DenoLand.Deno
```

### Setup and run

```sh
make setup   # creates .venv, installs backend and frontend dependencies
make run     # builds the frontend and starts the app
```

The app opens at **http://127.0.0.1:8000**. Stop it with Ctrl+C.
`make setup` uses uv when available, otherwise venv and pip. Choose a specific
Python with `make setup PYTHON=python3.12`. Setup does not modify global Python
packages or install system tools.

Windows without Make:

```powershell
py -3 scripts/setup.py
npm --prefix frontend run build
cd backend
..\.venv\Scripts\python.exe -m app
```

The first screen checks that ffmpeg, ffprobe, yt-dlp, and Deno are available
and shows how to fix anything missing.

## Development

```sh
make dev       # Vite on :5173 with hot reload, FastAPI on :8000 with auto-reload
make test      # pytest, TypeScript check, Vitest
make test-e2e  # Playwright end-to-end test (run against an empty data directory)
make build     # production frontend build into backend/static/
```

Test audio is generated with ffmpeg. Music files do not belong in the
repository. Interactive API documentation is available at `/docs` while the
app is running.

### Project layout

```
backend/
  app/
    api/         # routers: system, tracks, youtube, projects, jobs, exports
    audio/       # ffprobe, transcode, loudness, peaks, timeline, render
    importers/   # file upload and YouTube
    models.py    # SQLModel tables
    jobs.py      # background job runner
  tests/
frontend/
  src/
    components/  # Library, ClipEditor, MixList, MixPreview, ExportDialog, ...
    api/         # typed API client
    store/       # Zustand stores
    strings.ts   # all UI text in one place
  e2e/
scripts/         # setup and dev helpers
```

## Data and storage

Runtime data lives in `data/` (ignored by Git), or in the directory set by
`WEDDING_MIX_DATA_DIR`. It holds the untouched originals, working WAV copies
(stereo, 44.1 kHz, 16-bit), waveform peaks, previews, exports, and the SQLite
database `app.db`. Files are stored under generated IDs, not user-supplied
names. Back up the whole directory, or the Docker volume, to keep your Library.

## Troubleshooting

- **A tool shows as missing:** add it to `PATH`, restart the app, and press
  **Check again**.
- **YouTube imports fail:** update yt-dlp first.
  ```sh
  .venv/bin/python -m pip install -U 'yt-dlp[default]'
  # or, for a uv environment:
  uv pip install --python .venv/bin/python --upgrade 'yt-dlp[default]'
  ```
  On Windows, use `.venv\Scripts\python.exe`. See the
  [yt-dlp dependency notes](https://github.com/yt-dlp/yt-dlp#dependencies).

## Notes

This is a personal, offline tool. Only download and play music you have the
right to use. The design notes and original build plan are in
[DESIGN.md](DESIGN.md), [PRODUCT.md](PRODUCT.md), and
[the build plan](Wedding%20Mix%20Maker%20%E2%80%94%20Build%20Plan.md).
