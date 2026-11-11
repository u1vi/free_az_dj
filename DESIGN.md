---
name: Wedding Mix Maker
description: Plain and practical local music tools.
colors:
  accent: "#2b644a"
  surface: "#f5f6f4"
  ink: "#222b27"
  muted: "#5a655e"
  line: "#dce1db"
  button: "#ffffff"
  button-hover: "#e9eee8"
  button-disabled: "#ecefeb"
  button-disabled-text: "#677169"
  ready-surface: "#e8f0e9"
  ready-text: "#265639"
  warning-surface: "#fbefec"
  warning-text: "#8c3426"
  error: "#a1362c"
typography:
  headline:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  body:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  title:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "15px"
    fontWeight: 650
    lineHeight: 1.55
  label:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "13px"
    fontWeight: 600
  version:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  button: "7px"
  summary: "10px"
spacing:
  compact: "8px"
  related: "12px"
  summary-inset: "20px"
  row: "24px"
  desktop-inset: "48px"
  columns: "64px"
components:
  check-again:
    backgroundColor: "{colors.button}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.button}"
    padding: "8px 14px"
  check-again-hover:
    backgroundColor: "{colors.button-hover}"
  check-again-disabled:
    backgroundColor: "{colors.button-disabled}"
    textColor: "{colors.button-disabled-text}"
  ready-summary:
    backgroundColor: "{colors.ready-surface}"
    textColor: "{colors.ready-text}"
    rounded: "{rounded.summary}"
    padding: "20px"
  warning-summary:
    backgroundColor: "{colors.warning-surface}"
    textColor: "{colors.warning-text}"
    rounded: "{rounded.summary}"
    padding: "20px"
---

# Design System: Wedding Mix Maker

## Overview

**Creative North Star: "Plain and practical"**

A quiet, readable interface for a non-technical relative working on one laptop. Familiar controls, clear status labels, and generous separation help people understand what is ready and what needs attention. This record captures the implemented Setup and music Library system for reuse in later panels; `frontend/src/styles.css` owns detailed implementation values.

**Key Characteristics:**
- Light neutral surfaces and restrained green accents.
- Flat rows, compact supporting text, and visible recovery instructions.
- Standard local system sans typography.

## Colors

### Primary

The green accent identifies readiness, the product mark, the current milestone, and keyboard focus. Readiness summaries use their quieter tonal surface and text tokens.

### Neutral

The surface token is the page background; ink carries headings and body text. Muted supports descriptions and version strings. Line separates rows and page regions. The white button has distinct hover and disabled surfaces.

Warnings use a pale warm surface with dark red text. Individual failed tools use the error color alongside an icon, a named status, and recovery copy.

**The Named Status Rule.** Color always accompanies readable status text.

## Typography

Use the same local system sans stack throughout. There is no separate display, brand, or monospace family. Headline provides the page heading, title supports summaries and tool names, and label serves the refresh control. Supporting copy uses smaller sizes from the stylesheet. Version strings use tabular numerals and may wrap to prevent overflow.

## Layout

The shipped scope is desktop only; the build plan excludes a mobile layout. The page uses a centered container with a maximum width of 1440px. A flexible work area and a quiet right sidebar share a two-column grid. Setup uses the sidebar for milestone information; the Library uses it for actual song playback and clear notes about future editing features. At the existing 1100px breakpoint, horizontal padding and the column gap tighten, the sidebar narrows, and the section heading can wrap. The body retains a minimum width of 760px. The reviewed desktop widths are 1024px and 1440px.

Reuse the spacing roles above, with more space between regions than between related labels. Keep summaries, import controls, and flat information rows easy to scan. Composition specific to each surface remains in `.impeccable/setup-surface.md` and `.impeccable/library-surface.md`.

## Elevation & Depth

The implementation uses no shadows. Thin dividers establish regions; subtle background tones identify summaries and control states.

## Shapes

Controls and summaries have modest rounded corners. Dependency rows stay flat and separated by bottom borders. Small circular status and milestone markers support labels without becoming standalone controls.

## Components

The refresh button is white with a fine border and a short background-color transition. Hover changes its surface; keyboard focus uses the accent outline. During a request, the label changes to “Checking tools…” and the control is disabled. Reduced-motion preferences remove transitions.

Status summaries combine an icon, a short heading, and supporting text. Loading, readiness, missing tools, and connection failure share the same region. Changes are announced through a polite live region.

Dependency rows pair tool name and tabular version with a purpose description and a named status. Failed checks add specific recovery copy. Preserve this hierarchy when later panels need comparable system information.

The milestone sidebar uses numbered circles, concise descriptions, and explicit current or future labels. These entries are informational. Header navigation switches between Library and Setup with a visible current state. The shared green Add music button remains available across panels, except during an active upload; background conversion does not disable it.

Library inputs use the same system sans, ink, muted placeholders, green caret, and global focus outline. Search is a borderless field paired with a search icon; inline renaming uses a white field with a fine border, 5px corners, and explicit Save and Cancel actions. Ordinary buttons and icon actions retain 7px corners. Song titles wrap, original filenames truncate, and durations use tabular numerals.

The drop zone uses a pale neutral surface, a dashed border, and 10px corners. Dragging strengthens the green surface and border. Upload transfer and background import progress use thin green native progress bars with text and percentages. Ready, importing, and failed rows carry named states; failed imports add recovery copy and Retry when the original is available. Playback and removal are explicit row actions, with the selected song highlighted in the established green tones.

Song previews use native audio controls in the right column, preserving browser playback and seeking affordances. No editor panels or export dialogs are shipped yet.

## Do's and Don'ts

- **Do** pair status color with an icon and readable label.
- **Do** reuse the local system sans stack, flat separators, and restrained accent.
- **Do** show actual system state and actionable recovery copy.
- **Don't** represent future milestones as available controls.
- **Don't** add web fonts or decorative imagery to the plain, practical setup surface.
