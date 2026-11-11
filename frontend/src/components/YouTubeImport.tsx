import { useState, type FormEvent } from 'react';
import { api } from '../api/project';
import type { ImportJob } from '../api/library';
import { strings as s } from '../strings';
import { Modal } from './Modal';

interface Entry { url: string; title: string; duration_s: number | null }
interface Result { jobs: ImportJob[]; playlist?: Entry[]; warning?: string }
export function YouTubeImport({ refresh }: { refresh: () => Promise<void> }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const submit = async (event?: FormEvent, playlist?: string[]) => {
    event?.preventDefault(); if (!url.trim()) return;
    setBusy(true); setError(null); setWarning(null);
    try {
      const result = await api<Result>('/api/tracks/youtube', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.trim(), ...(playlist ? { playlist } : {}) }) });
      if (result.playlist) { setEntries(result.playlist); setSelected(result.playlist.map(entry => entry.url)); }
      else { setEntries(null); setUrl(''); }
      if (result.warning) setWarning(result.warning);
      await refresh();
    } catch (error) { setError(error instanceof Error ? error.message : s.youtube.failed); }
    finally { setBusy(false); }
  };
  return <div className="youtube-import"><form onSubmit={event => void submit(event)} className="youtube-form"><input type="url" aria-label={s.youtube.placeholder} placeholder={s.youtube.placeholder} value={url} onChange={event => setUrl(event.target.value)} required /><button className="button" disabled={busy || !url.trim()}>{busy ? s.youtube.checking : s.youtube.add}</button></form>
    {error && <p className="inline-error" role="alert">{error}</p>}{warning && <p className="inline-warning" role="status">{warning}</p>}
    {entries && <Modal titleId="playlist-title" onClose={() => setEntries(null)} busy={busy} className="playlist-dialog"><h2 id="playlist-title">{s.youtube.playlist}</h2><p>{s.youtube.playlistDescription}</p>{error && <p className="inline-error" role="alert">{error}</p>}{warning && <p className="inline-warning">{warning}</p>}<div className="playlist-select"><button className="text-button" onClick={() => setSelected(entries.map(entry => entry.url))}>{s.youtube.selectAll}</button><button className="text-button" onClick={() => setSelected([])}>{s.youtube.selectNone}</button></div><div className="playlist-entries">{entries.map(entry => <label key={entry.url}><input type="checkbox" checked={selected.includes(entry.url)} onChange={event => setSelected(current => event.target.checked ? [...current, entry.url] : current.filter(url => url !== entry.url))} /><span>{entry.title}</span>{entry.duration_s !== null && <small>{Math.floor(entry.duration_s / 60)}:{String(Math.floor(entry.duration_s % 60)).padStart(2, '0')}</small>}</label>)}</div><div className="modal-actions"><button className="button" disabled={busy} onClick={() => setEntries(null)}>{s.youtube.cancel}</button><button className="button button-primary" disabled={busy || !selected.length} onClick={() => void submit(undefined, selected)}>{busy ? s.youtube.checking : s.youtube.importSelected}</button></div></Modal>}
  </div>;
}
