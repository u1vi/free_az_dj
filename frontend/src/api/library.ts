import { strings as s } from '../strings';

export interface ImportJob {
  id: string; track_id: string; kind: string;
  status: 'queued' | 'running' | 'done' | 'error';
  progress: number; message: string;
  result_json: Record<string, unknown> | null;
}

export interface Track {
  id: string; title: string; original_name: string;
  source_type: 'upload' | 'youtube'; source_url: string | null;
  duration_s: number | null; loudness_lufs: number | null; true_peak_db: number | null;
  suggested_start_s: number; suggested_end_s: number | null;
  status: 'importing' | 'ready' | 'error'; error: string | null;
  created_at: string; job: ImportJob | null; can_retry: boolean;
}

function errorMessage(body: unknown): string {
  if (typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string') return body.detail;
  return s.library.requestFailed;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  try {
    const response = await fetch(path, { ...options, signal: AbortSignal.timeout(20_000), cache: 'no-store' });
    if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => null)));
    return response.status === 204 ? undefined as T : response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof TypeError || error instanceof DOMException) throw new Error(s.library.connectionFailed);
    throw error;
  }
}

export const listTracks = () => request<Track[]>('/api/tracks');
export const renameTrack = (id: string, title: string) => request<Track>(`/api/tracks/${id}`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }),
});
export const removeTrack = (id: string) => request<void>(`/api/tracks/${id}`, { method: 'DELETE' });
export const retryTrack = (id: string) => request<ImportJob>(`/api/tracks/${id}/retry`, { method: 'POST' });
export const audioUrl = (id: string) => `/api/tracks/${id}/audio`;

export function uploadTracks(files: File[], progress: (fraction: number) => void): Promise<ImportJob[]> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach(file => form.append('files', file));
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/tracks/upload');
    xhr.responseType = 'json';
    xhr.upload.onprogress = event => { if (event.lengthComputable) progress(event.loaded / event.total); };
    xhr.onerror = () => reject(new Error(s.library.uploadFailed));
    xhr.onabort = () => reject(new Error(s.library.uploadFailed));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as ImportJob[]);
      else reject(new Error(errorMessage(xhr.response)));
    };
    xhr.send(form);
  });
}
