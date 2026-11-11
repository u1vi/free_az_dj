import type { ImportJob, Track } from './library';
import { strings as s } from '../strings';

export interface Clip {
  id: string; project_id: string; track_id: string; position: number;
  start_s: number; end_s: number; fade_in_s: number; fade_out_s: number; gain_db: number;
  transition: 'crossfade' | 'gap' | 'cut'; transition_s: number; track: Track;
}
export interface Project {
  id: string; name: string; default_crossfade_s: number; normalize: boolean; target_lufs: number;
  updated_at: string; export_job_id: string | null; clips: Clip[]; warnings: string[];
}
export interface ExportOptions {
  format: 'mp3' | 'wav'; bitrate: number; sample_rate: number; bit_depth: number; also_separate_files: boolean;
}
export interface Job extends Omit<ImportJob, 'result_json'> {
  result_json: { preview_url?: string; songs?: { title: string; start_s: number }[]; mix_url?: string; tracklist_url?: string; separate_url?: string; duration_s?: number; loudness_lufs?: number | null; true_peak_db?: number | null; [key: string]: unknown } | null;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(path, { ...options, signal: AbortSignal.timeout(30_000), cache: 'no-store' }); }
  catch { throw new Error(s.library.connectionFailed); }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : s.library.requestFailed);
  }
  return response.json() as Promise<T>;
}
export const getProject = () => api<Project>('/api/projects/default');
export const saveProject = (project: Project) => api<Project>(`/api/projects/${project.id}`, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...project, clips: project.clips.map(({ track: _track, ...clip }) => clip) }),
});
export const getJob = (id: string) => api<Job>(`/api/jobs/${id}`);
export const startExport = (id: string, options: ExportOptions) => api<Job>(`/api/projects/${id}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options) });
export const previewTransition = (id: string, index: number) => api<Job>(`/api/projects/${id}/preview-transition`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clip_index: index }) });
export const previewMix = (id: string) => api<Job>(`/api/projects/${id}/preview-mix`, { method: 'POST' });
