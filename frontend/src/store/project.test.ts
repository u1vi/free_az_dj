import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../api/project';
import type { Track } from '../api/library';
import { flushSave, useProject } from './project';

const track: Track = { id: 'track', title: 'Song', original_name: 'song.wav', source_type: 'upload', source_url: null, duration_s: 100, loudness_lufs: -16, true_peak_db: -2, suggested_start_s: 0, suggested_end_s: 100, status: 'ready', error: null, created_at: '', job: null, can_retry: false };
const project: Project = { id: 'mix', name: 'Wedding', default_crossfade_s: 4, normalize: true, target_lufs: -14, updated_at: '', export_job_id: null, warnings: [], clips: [{ id: 'clip', project_id: 'mix', track_id: track.id, position: 0, start_s: 0, end_s: 100, fade_in_s: .5, fade_out_s: 2, gain_db: 0, transition: 'crossfade', transition_s: 4, track }] };

beforeEach(() => {
  vi.useFakeTimers(); vi.stubGlobal('window', globalThis);
  useProject.setState({ project: structuredClone(project), selectedId: 'clip', past: [], future: [], revision: 0, savedRevision: 0, saveStatus: 'saved', loading: false, error: null });
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('project editing and saving', () => {
  it('never lets a slow autosave overwrite a newer edit', async () => {
    const resolvers: ((response: Response) => void)[] = [];
    const fetch = vi.fn(() => new Promise<Response>(resolve => resolvers.push(resolve)));
    vi.stubGlobal('fetch', fetch);
    useProject.getState().updateClip('clip', { start_s: 1 });
    const pending = flushSave();
    useProject.getState().updateClip('clip', { start_s: 2 });
    resolvers[0](new Response(JSON.stringify({ ...project, clips: [{ ...project.clips[0], start_s: 1 }] })));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(useProject.getState().project!.clips[0].start_s).toBe(2);
    resolvers[1](new Response(JSON.stringify({ ...project, clips: [{ ...project.clips[0], start_s: 2 }] })));
    await pending;
    expect(useProject.getState().project!.clips[0].start_s).toBe(2);
    expect(useProject.getState().saveStatus).toBe('saved');
    expect(useProject.getState().savedRevision).toBe(2);
  });
  it('keeps changes and allows retry after a failed save', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'disk full' }), { status: 500 })).mockResolvedValueOnce(new Response(JSON.stringify({ ...project, name: 'Edited wedding' })));
    vi.stubGlobal('fetch', fetch);
    useProject.getState().edit(current => ({ ...current, name: 'Edited wedding' }));
    await expect(flushSave()).rejects.toThrow('disk full');
    expect(useProject.getState().project!.name).toBe('Edited wedding');
    expect(useProject.getState().saveStatus).toBe('error');
    await flushSave();
    expect(useProject.getState().saveStatus).toBe('saved');
  });
  it('keeps the last 50 states and supports undo and redo', () => {
    for (let index = 1; index <= 60; index++) useProject.getState().updateClip('clip', { start_s: index });
    expect(useProject.getState().past).toHaveLength(50);
    useProject.getState().undo(); expect(useProject.getState().project!.clips[0].start_s).toBe(59);
    useProject.getState().redo(); expect(useProject.getState().project!.clips[0].start_s).toBe(60);
  });
  it('refreshes the Library without erasing trim edits or order', () => {
    useProject.getState().updateClip('clip', { start_s: 3.05, end_s: 60.125 });
    const state = useProject.getState();
    useProject.getState().mergeTracks([{ ...track, title: 'Renamed song' }]);
    const current = useProject.getState();
    expect(current.project!.clips[0]).toMatchObject({ id: 'clip', start_s: 3.05, end_s: 60.125, track: { title: 'Renamed song' } });
    expect(current.revision).toBe(state.revision);
    expect(current.past).toHaveLength(state.past.length);
  });
});
