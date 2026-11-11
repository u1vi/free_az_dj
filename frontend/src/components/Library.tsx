import { useEffect, useRef, useState, type FormEvent } from 'react';
import { audioUrl, type Track } from '../api/library';
import type { LibraryState } from '../store/useLibrary';
import { strings as s } from '../strings';
import { ImportBar } from './ImportBar';
import { YouTubeImport } from './YouTubeImport';

function duration(seconds: number | null): string {
  if (seconds === null) return s.library.durationPending;
  const rounded = Math.floor(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}

function TrackRow({ track, library, onPlay, selected, onAdd }: { track: Track; library: LibraryState; onPlay: (track: Track) => void; selected: boolean; onAdd?: (track: Track) => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(track.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const progress = Math.max(0, Math.min(1, track.job?.progress ?? 0));
  const run = async (operation: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await operation(); return true; }
    catch (error) { setError(error instanceof Error ? error.message : s.library.requestFailed); return false; }
    finally { setBusy(false); }
  };
  const saveTitle = async (event: FormEvent) => {
    event.preventDefault();
    if (title.trim() && await run(() => library.rename(track.id, title.trim()))) setEditing(false);
  };
  return <li className={`track-row ${selected ? 'track-selected' : ''}`} data-track-id={track.id} onDoubleClick={event => { if (track.status === 'ready' && !(event.target as HTMLElement).closest('input,form,.track-actions')) onAdd?.(track); }}>
    <button className="icon-button play-button" type="button" onClick={() => onPlay(track)} disabled={track.status !== 'ready'} aria-label={s.library.playSong(track.title)} aria-pressed={selected}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m8 5 11 7-11 7Z" /></svg>
    </button>
    <div className="track-info">
      {editing ? <form className="rename-form" onSubmit={event => void saveTitle(event)}>
        <input aria-label={s.library.songName} value={title} onChange={event => setTitle(event.target.value)} maxLength={300} autoFocus onKeyDown={event => { if (event.key === 'Escape') { setEditing(false); setError(null); } }} />
        <button className="text-button" disabled={busy || !title.trim()} type="submit">{s.library.save}</button>
        <button className="text-button" disabled={busy} type="button" onClick={() => setEditing(false)}>{s.library.cancel}</button>
      </form> : <button type="button" className="track-title" onClick={() => { setTitle(track.title); setEditing(true); setError(null); }} title={s.library.renameSong(track.title)}>{track.title}</button>}
      <p className="track-metadata"><span>{track.source_type === 'youtube' ? s.library.youtubeSource : s.library.fileSource}</span><span className="track-original">{track.original_name}</span></p>
      {track.status === 'importing' && <div className="track-import"><div><span>{s.library.jobSteps[track.job?.message ?? ''] ?? s.library.importing}</span><span>{Math.round(progress * 100)}%</span></div><progress max="1" value={progress} aria-label={s.library.importProgress(track.title)} /></div>}
      {track.status === 'error' && <p className="track-error">{track.error ?? s.library.importFailed}</p>}
      {typeof track.job?.result_json?.warning === 'string' && <p className="inline-warning">{track.job.result_json.warning}</p>}
      {error && <p className="track-error" role="alert">{error}</p>}
    </div>
    <div className="track-state"><span className="track-duration">{duration(track.duration_s)}</span><span className={`track-status ${track.status === 'error' ? 'is-error' : track.status === 'ready' ? 'is-ready' : ''}`}>{s.library.trackStatuses[track.status]}</span></div>
    <div className="track-actions">
      {onAdd && track.status === 'ready' && <button className="text-button add-to-mix" type="button" aria-label={s.mix.addSong(track.title)} onClick={() => onAdd(track)}>{s.mix.addToMix}</button>}
      {track.status === 'error' && track.can_retry && <button className="text-button" type="button" onClick={() => void run(() => library.retry(track.id))} disabled={busy}>{s.library.retry}</button>}
      {track.status !== 'importing' && <button className="icon-button remove-button" type="button" onClick={() => void run(() => library.remove(track.id))} disabled={busy} aria-label={s.library.removeSong(track.title)}>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6" /></svg>
      </button>}
    </div>
  </li>;
}

export function Library({ library, chooseFiles, compact = false, onAdd }: { library: LibraryState; chooseFiles: () => void; compact?: boolean; onAdd?: (track: Track) => void }) {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [playError, setPlayError] = useState(false);
  const player = useRef<HTMLAudioElement>(null);
  const selected = library.tracks.find(track => track.id === selectedId && track.status === 'ready');
  const filtered = library.tracks.filter(track => track.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  useEffect(() => {
    if (!selected) return;
    setPlayError(false);
    void player.current?.play().catch(() => { /* Native controls remain available if autoplay is denied. */ });
  }, [selected?.id]);
  return <section className={`library-layout ${compact ? 'library-compact' : ''}`} aria-labelledby="library-heading">
    <div className="library-main">
      <div className="section-heading"><div><h1 id="library-heading">{s.library.title}</h1><p>{s.library.description}</p></div></div>
      <ImportBar chooseFiles={chooseFiles} importFiles={library.importFiles} upload={library.upload} error={library.uploadError} />
      <YouTubeImport refresh={library.refresh} />
      <div className="library-toolbar"><label className="search-field"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg><input type="search" aria-label={s.library.search} placeholder={s.library.search} value={search} onChange={event => setSearch(event.target.value)} /></label><span className="library-count">{s.library.songCount(library.tracks.length)}</span></div>
      {library.error && <div className="library-connection" role="alert"><p>{library.error}</p><button className="text-button" type="button" onClick={() => void library.refresh()}>{s.library.tryAgain}</button></div>}
      {library.loading ? <p className="library-empty" role="status">{s.library.loading}</p> : filtered.length ? <ul className="track-list">{filtered.map(track => <TrackRow key={track.id} track={track} library={library} selected={selectedId === track.id} onAdd={onAdd} onPlay={track => { setPlayError(false); setSelectedId(track.id); if (track.id === selectedId) void player.current?.play().catch(() => setPlayError(true)); }} />)}</ul> : <div className="library-empty"><h2>{search ? s.library.noMatches : s.library.emptyTitle}</h2><p>{search ? s.library.noMatchesDescription : s.library.emptyDescription}</p></div>}
      <p className="library-hint">{s.library.renameHint}</p>
      {compact && selected && <div className="compact-preview"><strong>{selected.title}</strong><audio key={selected.id} ref={player} src={audioUrl(selected.id)} controls preload="metadata" onError={() => setPlayError(true)} aria-label={s.library.playSong(selected.title)} />{playError && <p className="inline-error" role="alert">{s.library.playFailed}</p>}</div>}
    </div>
    {!compact && <aside className="library-preview" aria-labelledby="preview-heading">
      <h2 id="preview-heading">{s.library.previewTitle}</h2><p className="preview-intro">{s.library.previewDescription}</p>
      {selected ? <div className="preview-player"><h3>{selected.title}</h3><p>{duration(selected.duration_s)}</p><audio key={selected.id} ref={player} src={audioUrl(selected.id)} controls preload="metadata" onError={() => setPlayError(true)} aria-label={s.library.playSong(selected.title)} />{playError && <p className="inline-error" role="alert">{s.library.playFailed}</p>}</div> : <div className="preview-empty"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 14v-2a8 8 0 0 1 16 0v2M4 13h3v7H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1Zm16 0h-3v7h3a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1Z" /></svg><p>{s.library.choosePreview}</p></div>}
      <div className="library-next"><h2>{s.library.nextTitle}</h2><p>{s.library.nextDescription}</p><p>{s.library.alwaysAdd}</p></div>
    </aside>}
  </section>;
}
