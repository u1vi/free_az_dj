import { useState } from 'react';
import { DndContext, PointerSensor, KeyboardSensor, closestCenter, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy, sortableKeyboardCoordinates, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { getJob, previewTransition, type Clip } from '../api/project';
import { flushSave, useProject } from '../store/project';
import { formatTime, timeline } from '../utils/time';
import { strings as s } from '../strings';
import { MixPreview } from './MixPreview';

function MixItem({ clip, index, offset, count, warning }: { clip: Clip; index: number; offset: number; count: number; warning: boolean }) {
  const store = useProject();
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: clip.id });
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const move = (delta: number) => { const ids = store.project!.clips.map(item => item.id); store.reorder(arrayMove(ids, index, index + delta)); };
  const listen = async () => {
    if (!store.project) return;
    setPreviewing(true); setError(null); setPreview(null);
    try {
      await flushSave();
      let job = await previewTransition(store.project.id, index);
      for (let attempt = 0; attempt < 120 && job.status !== 'done' && job.status !== 'error'; attempt++) { await new Promise(resolve => window.setTimeout(resolve, 500)); job = await getJob(job.id); }
      if (job.status !== 'done' || !job.result_json?.preview_url) throw new Error(job.message || s.mix.previewFailed);
      setPreview(job.result_json.preview_url);
    } catch (error) { setError(error instanceof Error ? error.message : s.mix.previewFailed); }
    finally { setPreviewing(false); }
  };
  return <li ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`mix-item ${store.selectedId === clip.id ? 'mix-selected' : ''}`} data-clip-id={clip.id}>
    <div className="mix-item-main"><button className="icon-button drag-handle" aria-label={s.mix.drag(clip.track.title)} {...attributes} {...listeners}><svg width="16" height="20" viewBox="0 0 16 20" fill="currentColor" aria-hidden="true"><circle cx="5" cy="5" r="1" /><circle cx="11" cy="5" r="1" /><circle cx="5" cy="10" r="1" /><circle cx="11" cy="10" r="1" /><circle cx="5" cy="15" r="1" /><circle cx="11" cy="15" r="1" /></svg></button><span className="mix-index">{index + 1}</span><button className="mix-clip-title" aria-label={s.mix.select(clip.track.title)} onClick={() => store.select(clip.id)}><strong>{clip.track.title}</strong><span>{formatTime(clip.end_s - clip.start_s)} · {formatTime(offset)}</span></button><div className="mix-actions"><button className="text-button" disabled={index === 0} onClick={() => move(-1)}>{s.mix.moveUp}</button><button className="text-button" disabled={index === count - 1} onClick={() => move(1)}>{s.mix.moveDown}</button><button className="text-button" onClick={() => store.duplicateClip(clip.id)}>{s.mix.duplicate}</button><button className="text-button" onClick={() => store.removeClip(clip.id)}>{s.mix.remove}</button></div></div>
    {index < count - 1 && <div className="transition-row"><label>{s.mix.transition}<select aria-label={`${s.mix.transition} ${index + 1}`} value={clip.transition} onChange={event => store.updateClip(clip.id, { transition: event.target.value as Clip['transition'] })}><option value="crossfade">{s.mix.crossfade}</option><option value="gap">{s.mix.gap}</option><option value="cut">{s.mix.cut}</option></select></label>{clip.transition !== 'cut' && <label><input type="number" aria-label={`${s.mix.transitionSeconds} ${index + 1}`} min="0" max="120" step="0.1" value={clip.transition_s} onChange={event => store.updateClip(clip.id, { transition_s: Math.max(0, Number(event.target.value)) })} />{s.mix.seconds}</label>}<button className="text-button" disabled={previewing} onClick={() => void listen()}>{previewing ? s.mix.previewing : s.mix.preview}</button>{warning && <span className="inline-warning">{s.mix.crossfadeClamped}</span>}{preview && <audio src={preview} controls autoPlay aria-label={s.mix.preview} />}{error && <p className="inline-error" role="alert">{error}</p>}</div>}
  </li>;
}

export function MixList() {
  const store = useProject();
  const project = store.project;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  if (!project) return null;
  const timing = timeline(project.clips);
  return <section className="mix-list-section" aria-labelledby="mix-order-heading"><div className="mix-list-heading"><div><h2 id="mix-order-heading">{s.mix.mixList}</h2><p>{s.mix.songs(project.clips.length)} · {s.mix.total} <strong>{formatTime(timing.total)}</strong></p></div><label>{s.mix.defaultCrossfade}<input type="number" aria-label={s.mix.defaultCrossfade} min="0" max="30" step="0.1" value={project.default_crossfade_s} onChange={event => store.edit(current => ({ ...current, default_crossfade_s: Math.max(0, Number(event.target.value)) }))} /><span>{s.mix.seconds}</span></label></div>
    {project.clips.length > 0 && <MixPreview project={project} />}
    {project.clips.length ? <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => { if (over && active.id !== over.id) { const ids = project.clips.map(clip => clip.id); store.reorder(arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id)))); } }}><SortableContext items={project.clips.map(clip => clip.id)} strategy={verticalListSortingStrategy}><ol className="mix-list">{project.clips.map((clip, index) => <MixItem key={clip.id} clip={clip} index={index} offset={timing.offsets[index]} count={project.clips.length} warning={timing.clamped.includes(index)} />)}</ol></SortableContext></DndContext> : <div className="mix-empty"><h3>{s.mix.empty}</h3><p>{s.mix.emptyDescription}</p></div>}
    {project.warnings?.map((warning, index) => <p className="inline-warning" key={index}>{warning}</p>)}
  </section>;
}
