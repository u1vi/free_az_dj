import { useEffect, useRef, useState } from 'react';
import { getJob, previewMix, type Job, type Project } from '../api/project';
import { flushSave, useProject } from '../store/project';
import { formatTime } from '../utils/time';
import { strings as s } from '../strings';

interface Rendered { url: string; songs: { title: string; start_s: number }[]; key: string }

// Everything that changes how the mix sounds; renames and selection do not.
function audible(project: Project): string {
  return JSON.stringify([project.normalize, project.target_lufs, project.clips.map(clip => [clip.track_id, clip.start_s, clip.end_s, clip.fade_in_s, clip.fade_out_s, clip.gain_db, clip.transition, clip.transition_s])]);
}

export function MixPreview({ project }: { project: Project }) {
  const [job, setJob] = useState<Job | null>(null);
  const [rendered, setRendered] = useState<Rendered | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const player = useRef<HTMLAudioElement>(null);
  const pendingKey = useRef('');
  const jobId = job?.id;
  const running = starting || job?.status === 'queued' || job?.status === 'running';
  useEffect(() => {
    if (!jobId) return;
    let active = true; let timeout: number | undefined;
    const poll = async () => {
      try {
        const next = await getJob(jobId); if (!active) return;
        setJob(next); setError(null);
        if (next.status === 'queued' || next.status === 'running') timeout = window.setTimeout(() => void poll(), 1000);
        else if (next.status === 'done' && next.result_json?.preview_url) { setRendered({ url: next.result_json.preview_url, songs: next.result_json.songs ?? [], key: pendingKey.current }); setTime(0); }
        else setError(next.message || s.mix.fullPreviewFailed);
      } catch (error) { if (active) { setError(error instanceof Error ? error.message : s.mix.fullPreviewFailed); timeout = window.setTimeout(() => void poll(), 3000); } }
    };
    timeout = window.setTimeout(() => void poll(), 500);
    return () => { active = false; window.clearTimeout(timeout); };
  }, [jobId]);
  const listen = async () => {
    setStarting(true); setError(null);
    try { await flushSave(); pendingKey.current = audible(useProject.getState().project ?? project); setJob(await previewMix(project.id)); }
    catch (error) { setError(error instanceof Error ? error.message : s.mix.fullPreviewFailed); }
    finally { setStarting(false); }
  };
  const outdated = rendered !== null && rendered.key !== audible(project);
  const current = rendered?.songs.reduce((found, song, index) => song.start_s <= time + 0.05 ? index : found, -1) ?? -1;
  const playFrom = (seconds: number) => { const audio = player.current; if (!audio) return; audio.currentTime = seconds; void audio.play().catch(() => { /* Native controls remain available. */ }); };
  return <div className="mix-preview">
    <div className="mix-preview-heading"><div><h3>{s.mix.listenFull}</h3><p>{s.mix.listenFullDescription}</p></div>{!running && <button type="button" className={`button ${rendered && !outdated ? '' : 'button-primary'}`} onClick={() => void listen()}>{rendered ? s.mix.updatePreview : s.mix.listenFull}</button>}</div>
    {running && <div className="mix-preview-progress" role="status"><div><span>{s.mix.preparingFull}</span><span>{Math.round((job?.progress ?? 0) * 100)}%</span></div><progress max="1" value={job?.progress ?? 0} aria-label={s.mix.preparingFull} /></div>}
    {outdated && !running && <p className="inline-warning" role="status">{s.mix.previewOutdated}</p>}
    {rendered && <><audio key={rendered.url} ref={player} src={rendered.url} controls autoPlay preload="metadata" aria-label={s.mix.listenFull} onTimeUpdate={event => setTime(event.currentTarget.currentTime)} />
      <ol className="mix-preview-songs">{rendered.songs.map((song, index) => <li key={index}><button type="button" aria-current={index === current ? 'true' : undefined} aria-label={s.mix.playFrom(song.title)} onClick={() => playFrom(song.start_s)}><span className="mix-preview-time">{formatTime(song.start_s)}</span><span className="mix-preview-title">{index + 1}. {song.title}</span>{index === current && <span className="visually-hidden">{s.mix.nowPlaying}</span>}</button></li>)}</ol></>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
