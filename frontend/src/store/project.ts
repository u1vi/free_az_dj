import { create } from 'zustand';
import { getProject, saveProject, type Clip, type Project } from '../api/project';
import type { Track } from '../api/library';
import { strings as s } from '../strings';

type SaveStatus = 'saved' | 'saving' | 'error';
interface ProjectState {
  project: Project | null; selectedId: string | null; loading: boolean; error: string | null;
  saveStatus: SaveStatus; revision: number; savedRevision: number; past: Project[]; future: Project[];
  load: () => Promise<void>; edit: (change: (project: Project) => Project) => void;
  updateClip: (id: string, change: Partial<Clip>) => void; addTrack: (track: Track) => void;
  removeClip: (id: string) => void; duplicateClip: (id: string) => void; reorder: (ids: string[]) => void;
  select: (id: string | null) => void; undo: () => void; redo: () => void;
  mergeTracks: (tracks: Track[]) => void; setExportJob: (id: string) => void;
}
let timer: number | undefined;
let saving: Promise<void> | null = null;
let loading: Promise<void> | null = null;
function scheduleSave() { window.clearTimeout(timer); timer = window.setTimeout(() => { void flushSave().catch(() => {}); }, 800); }
export const useProject = create<ProjectState>((set, get) => ({
  project: null, selectedId: null, loading: true, error: null, saveStatus: 'saved', revision: 0, savedRevision: 0, past: [], future: [],
  load: () => {
    if (get().project) return Promise.resolve();
    if (loading) return loading;
    set({ loading: true, error: null });
    loading = getProject().then(project => set({ project, selectedId: project.clips[0]?.id ?? null, loading: false })).catch(error => set({ loading: false, error: error instanceof Error ? error.message : s.mix.loadFailed })).finally(() => { loading = null; });
    return loading;
  },
  edit: change => {
    const current = get(); if (!current.project) return;
    const project = change(structuredClone(current.project));
    project.clips = project.clips.map((clip, position) => ({ ...clip, position }));
    set({ project, past: [...current.past.slice(-49), current.project], future: [], revision: current.revision + 1, saveStatus: 'saving' }); scheduleSave();
  },
  updateClip: (id, change) => get().edit(project => ({ ...project, clips: project.clips.map(clip => clip.id === id ? { ...clip, ...change } : clip) })),
  addTrack: track => {
    const project = get().project; if (!project || track.status !== 'ready' || !track.duration_s) return;
    const id = crypto.randomUUID();
    const start = track.suggested_start_s; const end = track.suggested_end_s ?? track.duration_s;
    get().edit(current => ({ ...current, clips: [...current.clips, { id, project_id: current.id, track_id: track.id, position: current.clips.length, start_s: start, end_s: end, fade_in_s: 0.5, fade_out_s: 2, gain_db: 0, transition: 'crossfade', transition_s: current.default_crossfade_s, track }] }));
    set({ selectedId: id });
  },
  removeClip: id => { get().edit(project => ({ ...project, clips: project.clips.filter(clip => clip.id !== id) })); const current = get(); if (current.selectedId === id) set({ selectedId: current.project?.clips[0]?.id ?? null }); },
  duplicateClip: id => {
    const duplicate = crypto.randomUUID();
    get().edit(project => { const index = project.clips.findIndex(clip => clip.id === id); if (index >= 0) project.clips.splice(index + 1, 0, { ...project.clips[index], id: duplicate }); return project; }); set({ selectedId: duplicate });
  },
  reorder: ids => get().edit(project => ({ ...project, clips: ids.map(id => project.clips.find(clip => clip.id === id)!).filter(Boolean) })),
  select: selectedId => set({ selectedId }),
  undo: () => { const current = get(); const project = current.past.at(-1); if (!project || !current.project) return; set({ project, past: current.past.slice(0, -1), future: [current.project, ...current.future].slice(0, 50), revision: current.revision + 1, saveStatus: 'saving', selectedId: project.clips.some(clip => clip.id === current.selectedId) ? current.selectedId : project.clips[0]?.id ?? null }); scheduleSave(); },
  redo: () => { const current = get(); const project = current.future[0]; if (!project || !current.project) return; set({ project, past: [...current.past, current.project].slice(-50), future: current.future.slice(1), revision: current.revision + 1, saveStatus: 'saving', selectedId: project.clips.some(clip => clip.id === current.selectedId) ? current.selectedId : project.clips[0]?.id ?? null }); scheduleSave(); },
  mergeTracks: tracks => set(current => current.project ? { project: { ...current.project, clips: current.project.clips.map(clip => ({ ...clip, track: tracks.find(track => track.id === clip.track_id) ?? clip.track })) } } : {}),
  setExportJob: id => set(current => current.project ? { project: { ...current.project, export_job_id: id } } : {}),
}));

export async function flushSave(): Promise<void> {
  window.clearTimeout(timer);
  if (saving) { await saving; if (useProject.getState().revision !== useProject.getState().savedRevision) return flushSave(); return; }
  const state = useProject.getState(); if (!state.project || state.revision === state.savedRevision) return;
  saving = (async () => {
    const snapshot = useProject.getState();
    useProject.setState({ saveStatus: 'saving' });
    try {
      const response = await saveProject(snapshot.project!);
      const current = useProject.getState();
      useProject.setState({ savedRevision: snapshot.revision, saveStatus: current.revision === snapshot.revision ? 'saved' : 'saving', ...(current.revision === snapshot.revision ? { project: response } : {}) });
    } catch (error) { useProject.setState({ saveStatus: 'error' }); throw error; }
  })();
  try { await saving; } finally { saving = null; }
  if (useProject.getState().revision !== useProject.getState().savedRevision) return flushSave();
}
