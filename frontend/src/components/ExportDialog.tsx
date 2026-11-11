import { useEffect, useState } from 'react';
import { getJob, startExport, type ExportOptions, type Job } from '../api/project';
import { flushSave, useProject } from '../store/project';
import { strings as s } from '../strings';
import { Modal } from './Modal';

export function ExportDialog({ onClose }: { onClose: () => void }) {
  const store = useProject();
  const [options, setOptions] = useState<ExportOptions>({ format: 'mp3', bitrate: 320, sample_rate: 44100, bit_depth: 16, also_separate_files: false });
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState(store.project?.export_job_id ?? null);
  const running = job?.status === 'running' || job?.status === 'queued';
  useEffect(() => {
    if (!jobId) return;
    let active = true; let timeout: number | undefined;
    const poll = async () => {
      try { const next = await getJob(jobId); if (!active) return; setJob(next); setError(null); if (next.status === 'queued' || next.status === 'running') timeout = window.setTimeout(() => void poll(), 1000); }
      catch (error) { if (active) { setError(error instanceof Error ? error.message : s.exportDialog.failed); timeout = window.setTimeout(() => void poll(), 3000); } }
    };
    void poll(); return () => { active = false; window.clearTimeout(timeout); };
  }, [jobId]);
  const begin = async () => {
    if (!store.project) return;
    setSubmitting(true); setError(null);
    try { await flushSave(); const next = await startExport(store.project.id, options); setJob(next); setJobId(next.id); store.setExportJob(next.id); }
    catch (error) { setError(error instanceof Error ? error.message : s.exportDialog.failed); }
    finally { setSubmitting(false); }
  };
  // A finished export is only offered while the saved mix is still the one it rendered.
  const outdated = job?.status === 'done' && (job.result_json?.project_updated_at !== store.project?.updated_at || store.revision !== store.savedRevision);
  const result = outdated ? null : job?.result_json;
  return <Modal titleId="export-title" onClose={onClose} className="export-dialog"><div className="modal-heading"><h2 id="export-title">{s.exportDialog.title}</h2><button className="text-button" onClick={onClose}>{s.exportDialog.close}</button></div>
    {!running && <div className="export-settings"><label>{s.exportDialog.format}<select value={options.format} onChange={event => setOptions({ ...options, format: event.target.value as 'mp3' | 'wav' })}><option value="mp3">MP3</option><option value="wav">WAV</option></select></label>{options.format === 'mp3' && <label>{s.exportDialog.bitrate}<select value={options.bitrate} onChange={event => setOptions({ ...options, bitrate: Number(event.target.value) })}>{[192, 256, 320].map(value => <option key={value} value={value}>{value} kbps</option>)}</select></label>}
      <label className="checkbox-label"><input type="checkbox" checked={store.project?.normalize ?? true} onChange={event => store.edit(project => ({ ...project, normalize: event.target.checked }))} />{s.mix.normalizing}</label><label className="checkbox-label"><input type="checkbox" checked={options.also_separate_files} onChange={event => setOptions({ ...options, also_separate_files: event.target.checked })} />{s.exportDialog.separate}</label><p className="small-copy">{s.exportDialog.separateDescription}</p><details><summary>{s.exportDialog.advanced}</summary><div className="export-advanced"><label>{s.exportDialog.sampleRate}<select value={options.sample_rate} onChange={event => setOptions({ ...options, sample_rate: Number(event.target.value) })}><option value="44100">44.1 kHz</option><option value="48000">48 kHz</option></select></label>{options.format === 'wav' && <label>{s.exportDialog.bitDepth}<select value={options.bit_depth} onChange={event => setOptions({ ...options, bit_depth: Number(event.target.value) })}><option value="16">16 bit</option><option value="24">24 bit</option></select></label>}<label>{s.mix.target}<input type="number" min="-30" max="-9" step="1" value={store.project?.target_lufs ?? -14} onChange={event => store.edit(project => ({ ...project, target_lufs: Number(event.target.value) }))} /></label></div></details></div>}
    {outdated && <p className="inline-warning" role="status">{s.exportDialog.outdated}</p>}
    {job && !outdated && <div className="export-progress" role="status"><h3>{job.status === 'done' ? s.exportDialog.done : job.status === 'error' ? s.exportDialog.failed : s.exportDialog.exporting}</h3><p>{job.message}</p>{running && <><progress value={job.progress} max="1" aria-label={s.exportDialog.exporting} /><p>{Math.round(job.progress * 100)}% · {s.exportDialog.resume}</p></>}</div>}
    {job?.status === 'done' && result && <div className="export-downloads">{result.mix_url && <a className="button button-primary" href={result.mix_url} download>{s.exportDialog.download}</a>}{result.tracklist_url && <a className="button" href={result.tracklist_url} download>{s.exportDialog.tracklist}</a>}{result.separate_url && <a className="button" href={result.separate_url} download>{s.exportDialog.zip}</a>}<p>{s.exportDialog.check}: {s.exportDialog.loudness} {typeof result.loudness_lufs === 'number' ? `${result.loudness_lufs.toFixed(1)} LUFS` : s.exportDialog.noMeasurement} · {s.exportDialog.truePeak} {typeof result.true_peak_db === 'number' ? `${result.true_peak_db.toFixed(1)} dBTP` : s.exportDialog.noMeasurement}</p></div>}
    {error && <p className="inline-error" role="alert">{error}</p>}{!running && <div className="modal-actions"><button className="button button-primary" disabled={submitting || !store.project?.clips.length} onClick={() => void begin()}>{submitting ? s.exportDialog.exporting : job?.status === 'error' ? s.exportDialog.retry : s.exportDialog.start}</button></div>}
  </Modal>;
}
