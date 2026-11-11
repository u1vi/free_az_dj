import { useEffect, useId, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import Regions, { type Region } from 'wavesurfer.js/dist/plugins/regions.esm.js';
import Timeline from 'wavesurfer.js/dist/plugins/timeline.esm.js';
import Zoom from 'wavesurfer.js/dist/plugins/zoom.esm.js';
import type { Clip } from '../api/project';
import { audioUrl } from '../api/library';
import { useProject } from '../store/project';
import { formatTime, parseTime } from '../utils/time';
import { strings as s } from '../strings';

function TimeField({ label, value, onChange }: { label: string; value: number; onChange: (seconds: number) => boolean }) {
  const errorId = useId();
  const [text, setText] = useState(formatTime(value, true));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { setText(formatTime(value, true)); setInvalid(false); }, [value]);
  const commit = () => { const seconds = parseTime(text); const valid = seconds !== null && onChange(seconds); setInvalid(!valid); if (valid) setText(formatTime(seconds, true)); };
  return <label className="time-field"><span>{label}</span><input aria-label={label} aria-invalid={invalid} aria-describedby={invalid ? errorId : undefined} value={text} onChange={event => setText(event.target.value)} onBlur={commit} onKeyDown={event => { if (event.key === 'Enter') { commit(); event.currentTarget.blur(); } if (event.key === 'Escape') { setText(formatTime(value, true)); setInvalid(false); } }} />{invalid && <small id={errorId} className="inline-error">{s.mix.timeInvalid}</small>}</label>;
}

export function ClipEditor({ clip }: { clip: Clip | undefined }) {
  const element = useRef<HTMLDivElement>(null);
  const wave = useRef<WaveSurfer | null>(null);
  const region = useRef<Region | null>(null);
  const latest = useRef(clip); latest.current = clip;
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [zoom, setZoom] = useState(0);
  const [playing, setPlaying] = useState(false);
  const updateClip = useProject(state => state.updateClip);
  const duration = clip?.track.duration_s ?? 0;
  const setTrim = (side: 'start_s' | 'end_s', value: number) => {
    const current = latest.current; if (!current || !Number.isFinite(value)) return false;
    const start = side === 'start_s' ? value : current.start_s;
    const end = side === 'end_s' ? value : current.end_s;
    if (start < 0 || end > (current.track.duration_s ?? 0) + 0.00001 || end - start < 0.001) return false;
    if (current[side] !== value) updateClip(current.id, { [side]: Math.round(value * 1000) / 1000 });
    return true;
  };
  useEffect(() => {
    if (!clip || !element.current) return;
    const abort = new AbortController(); let disposed = false;
    setReady(false); setFailed(false); setPlayhead(clip.start_s); setZoom(0); setPlaying(false);
    const initialise = async () => {
      try {
        const response = await fetch(`/api/tracks/${clip.track_id}/peaks`, { signal: abort.signal });
        if (!response.ok) throw new Error('peaks');
        const peaks = await response.json() as { duration: number; peaks: number[] };
        if (disposed || !element.current) return;
        const regions = Regions.create();
        const player = WaveSurfer.create({ container: element.current, waveColor: '#8da591', progressColor: '#2b644a', cursorColor: '#222b27', cursorWidth: 2, height: 160, normalize: false, autoScroll: true, autoCenter: true, dragToSeek: true, plugins: [regions, Timeline.create({ height: 22, style: { color: '#5a655e', fontSize: '10px' } }), Zoom.create({ scale: 0.15, maxZoom: 800 })] });
        wave.current = player;
        regions.on('region-updated', value => { const current = latest.current; if (current) updateClip(current.id, { start_s: Math.round(value.start * 1000) / 1000, end_s: Math.round(value.end * 1000) / 1000 }); });
        player.on('timeupdate', time => setPlayhead(time));
        // The waveform's own media element is outside the page, so pause page players directly.
        player.on('play', () => { setPlaying(true); document.querySelectorAll('audio').forEach(audio => audio.pause()); }); player.on('pause', () => setPlaying(false));
        player.on('error', () => { if (!disposed) setFailed(true); });
        player.on('zoom', pixels => setZoom(pixels));
        await player.load(audioUrl(clip.track_id), [peaks.peaks], peaks.duration);
        if (disposed) return;
        const current = latest.current!;
        region.current = regions.addRegion({ id: current.id, start: current.start_s, end: current.end_s, drag: true, resize: true, minLength: 0.001, color: 'rgba(43,100,74,.16)' });
        player.setTime(current.start_s); setReady(true);
      } catch (error) { if (!disposed && !(error instanceof DOMException && error.name === 'AbortError')) setFailed(true); }
    };
    void initialise();
    return () => { disposed = true; abort.abort(); wave.current?.destroy(); wave.current = null; region.current = null; };
  }, [clip?.id, clip?.track_id, updateClip]);
  useEffect(() => { if (clip && region.current) region.current.setOptions({ start: clip.start_s, end: clip.end_s }); }, [clip?.start_s, clip?.end_s]);
  const play = (start: number, end: number) => { if (!ready) return; void wave.current?.play(start, end).catch(() => setFailed(true)); };
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('input,select,textarea,button,a,audio,[contenteditable="true"],[role="dialog"],dialog') || event.ctrlKey || event.metaKey || !wave.current || !ready || !latest.current) return;
      const current = latest.current;
      if (event.code === 'Space') { event.preventDefault(); void wave.current.playPause().catch(() => setFailed(true)); }
      if (event.key.toLowerCase() === 'i') { event.preventDefault(); setTrim('start_s', wave.current.getCurrentTime()); }
      if (event.key.toLowerCase() === 'o') { event.preventDefault(); setTrim('end_s', wave.current.getCurrentTime()); }
      if (event.key.toLowerCase() === 'p') { event.preventDefault(); void wave.current.play(current.start_s, current.end_s).catch(() => setFailed(true)); }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); const delta = (event.shiftKey ? 0.1 : 1) * (event.key === 'ArrowLeft' ? -1 : 1); wave.current.setTime(Math.max(0, Math.min(current.track.duration_s ?? 0, wave.current.getCurrentTime() + delta))); }
    };
    window.addEventListener('keydown', keyboard); return () => window.removeEventListener('keydown', keyboard);
  }, [ready]);
  useEffect(() => {
    const pause = () => wave.current?.pause();
    document.addEventListener('play', pause, true); return () => document.removeEventListener('play', pause, true);
  }, []);
  if (!clip) return <section className="clip-editor editor-empty"><h2>{s.mix.editorEmpty}</h2><p>{s.mix.editorEmptyDescription}</p></section>;
  const automatic = useProject.getState().project?.normalize && clip.track.loudness_lufs !== null ? Math.min(12, (useProject.getState().project?.target_lufs ?? -14) - clip.track.loudness_lufs) : 0;
  return <section className="clip-editor" aria-labelledby="clip-editor-heading"><div className="editor-heading"><div><h2 id="clip-editor-heading">{clip.track.title}</h2><p>{s.mix.editor}</p></div><span className="editor-length">{s.mix.length} <strong>{formatTime(clip.end_s - clip.start_s, true)}</strong></span></div>
    <div className="wave-panel" aria-label={s.mix.selected}><div ref={element} className="waveform" data-testid="waveform" />{!ready && !failed && <p role="status">{s.mix.waveformLoading}</p>}{failed && <p className="inline-error" role="alert">{s.mix.waveformError}</p>}</div>
    <div className="wave-toolbar"><span>{s.mix.playhead} <output aria-label={s.mix.playhead}>{formatTime(playhead, true)}</output></span><label>{s.mix.zoom}<input type="range" aria-label={s.mix.zoom} min="0" max="800" step="5" value={Math.min(800, zoom)} disabled={!ready} onChange={event => { const value = Number(event.target.value); setZoom(value); wave.current?.zoom(value); }} /></label></div>
    <div className="trim-fields">{(['start_s', 'end_s'] as const).map(side => <div key={side}><TimeField label={side === 'start_s' ? s.mix.start : s.mix.end} value={clip[side]} onChange={value => setTrim(side, value)} /><div className="nudge-buttons">{[-1, -0.1, 0.1, 1].map(delta => <button type="button" key={delta} aria-label={`${side === 'start_s' ? s.mix.start : s.mix.end} ${delta > 0 ? '+' : ''}${delta} ${s.mix.seconds}`} onClick={() => setTrim(side, Math.max(0, Math.min(duration, clip[side] + delta)))}>{delta > 0 ? '+' : ''}{delta}s</button>)}</div></div>)}</div>
    <div className="play-controls"><button className="button button-primary" disabled={!ready} onClick={() => { if (playing) wave.current?.pause(); else play(clip.start_s, clip.end_s); }} aria-label={s.mix.playPause}><svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{playing ? <path d="M7 4v12m6-12v12" /> : <path d="m6 3 10 7-10 7Z" />}</svg>{s.mix.playSelection}</button><button className="button" disabled={!ready} onClick={() => play(clip.start_s, Math.min(clip.end_s, clip.start_s + 5))}>{s.mix.playFirst}</button><button className="button" disabled={!ready} onClick={() => play(Math.max(clip.start_s, clip.end_s - 5), clip.end_s)}>{s.mix.playLast}</button></div>
    <div className="clip-sliders">{(['fade_in_s', 'fade_out_s', 'gain_db'] as const).map(field => <label key={field}><span>{field === 'fade_in_s' ? s.mix.fadeIn : field === 'fade_out_s' ? s.mix.fadeOut : s.mix.gain}<output>{clip[field].toFixed(1)} {field === 'gain_db' ? s.mix.db : 's'}</output></span><input type="range" aria-label={field === 'fade_in_s' ? s.mix.fadeIn : field === 'fade_out_s' ? s.mix.fadeOut : s.mix.gain} min={field === 'gain_db' ? -12 : 0} max={field === 'gain_db' ? 12 : 10} step="0.1" value={clip[field]} onChange={event => updateClip(clip.id, { [field]: Number(event.target.value) })} /></label>)}</div>
    <div className="editor-footer"><button className="text-button" onClick={() => updateClip(clip.id, { start_s: clip.track.suggested_start_s, end_s: clip.track.suggested_end_s ?? duration })}>{s.mix.trimSilence}</button><button className="text-button" onClick={() => updateClip(clip.id, { gain_db: 0 })}>{s.mix.reset} {s.mix.gain}</button><span>{clip.track.loudness_lufs === null ? s.mix.loudnessUnknown : s.mix.loudness(clip.track.loudness_lufs, automatic + clip.gain_db)}</span></div>
  </section>;
}
