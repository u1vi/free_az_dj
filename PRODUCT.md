# Wedding Mix Maker

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

The build plan specifies Python 3.11+, FastAPI, Uvicorn, React, TypeScript,
Vite, Tailwind CSS, ffmpeg, yt-dlp, Deno, and SQLite via SQLModel.

## Users

A family preparing music for a rural wedding without a DJ. A non-technical
relative must be able to use the finished app.

## Product Purpose

Import songs, trim them, order them with smooth transitions, and export one mix.
The complete scope and milestone acceptance checks live in
`Wedding Mix Maker — Build Plan.md`.

## Operating Context

One laptop, local files, no account, and no hosting. Internet is needed for
installation and YouTube imports; working with local music stays offline.

## Capabilities and Constraints

Build the milestones in order and stop after each for review. Milestone 1
provided the runnable skeleton and dependency screen. Milestone 2 adds local
file import, durable background jobs, and the Library with search, renaming,
playback, removal, and retry. Stop for review before YouTube import in milestone
3, trimming and arranging in milestone 4, and export in milestone 5. Bind native
servers to 127.0.0.1. All audio processing belongs on the backend. No
mobile-specific layout, DJ effects, or cloud features.

The user explicitly requires adding music while trimming and arranging. Keep
the Library and Add music control available throughout that workspace; importing
more songs must preserve existing trim edits and mix order. New imports become
Library entries rather than resetting or replacing the current mix. The tasks
are not locked wizard stages.

The user also requested Docker support. The container listens on its internal
network interface; Compose publishes its port only on host 127.0.0.1. A named
volume persists runtime data separately from the native app's data directory.

## Brand Commitments

The user chose a plain, practical interface. Keep UI copy in English in one
strings file so it can later be translated into Azerbaijani.

## Product Principles

- Show actual system state and an actionable recovery when something fails.
- Prefer simple controls and familiar language.
- Keep music and project data on the laptop.
- Do not present future capabilities as working controls.

