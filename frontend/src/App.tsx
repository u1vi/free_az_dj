import { useEffect, useRef, useState } from 'react';
import { Library } from './components/Library';
import { SetupPanel } from './components/SetupPanel';
import { ClipEditor } from './components/ClipEditor';
import { MixList } from './components/MixList';
import { ExportDialog } from './components/ExportDialog';
import { Modal } from './components/Modal';
import { useLibrary } from './store/useLibrary';
import { flushSave, useProject } from './store/project';
import { strings as s } from './strings';

export function App() {
  const [panel, setPanel] = useState<'mix' | 'setup'>('mix');
  const [exportOpen, setExportOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const library = useLibrary();
  const store = useProject();
  const chooseFiles = () => fileInput.current?.click();
  const importing = library.tracks.filter(track => track.status === 'importing').length;
  useEffect(() => { void useProject.getState().load(); }, []);
  useEffect(() => {
    // One player at a time: starting any song, transition or mix preview pauses the others.
    const exclusive = (event: Event) => document.querySelectorAll('audio').forEach(audio => { if (audio !== event.target) audio.pause(); });
    document.addEventListener('play', exclusive, true);
    return () => document.removeEventListener('play', exclusive, true);
  }, []);
  useEffect(() => { useProject.getState().mergeTracks(library.tracks); }, [library.tracks, store.project?.id]);
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).closest('input,select,textarea,[contenteditable="true"],[role="dialog"],dialog')) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); if (event.shiftKey) useProject.getState().redo(); else useProject.getState().undo(); }
      if (event.key === 'Delete' && panel === 'mix') { const current = useProject.getState(); if (current.selectedId) { event.preventDefault(); current.removeClip(current.selectedId); } }
    };
    const beforeUnload = (event: BeforeUnloadEvent) => { const current = useProject.getState(); if (current.revision !== current.savedRevision) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('keydown', keyboard); window.addEventListener('beforeunload', beforeUnload);
    return () => { window.removeEventListener('keydown', keyboard); window.removeEventListener('beforeunload', beforeUnload); };
  }, [panel]);
  const selected = store.project?.clips.find(clip => clip.id === store.selectedId);
  return <div className="app-shell full-workspace">
    <header className="app-header"><div className="flex items-center gap-3"><svg className="app-mark" width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M5 13v6m5-10v14m6-18v22m6-18v14m5-10v6" /></svg><span className="app-name">{s.appName}</span></div>
      <div className="header-actions"><nav className="panel-nav" aria-label={s.library.navigation}><button type="button" aria-current={panel === 'mix' ? 'page' : undefined} onClick={() => setPanel('mix')}>{s.mix.workspace}</button><button type="button" aria-current={panel === 'setup' ? 'page' : undefined} onClick={() => setPanel('setup')}>{s.setup}</button></nav><button className="button" type="button" onClick={chooseFiles} disabled={Boolean(library.upload)}>{s.library.addMusic}</button><button className="button button-primary" type="button" disabled={!store.project?.clips.length || store.loading} onClick={() => setExportOpen(true)}>{s.mix.export}</button></div>
    </header>
    <input ref={fileInput} className="visually-hidden" type="file" multiple aria-label={s.library.chooseFiles} tabIndex={-1} onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = ''; void library.importFiles(files); }} />
    {panel === 'mix' ? <main className="workspace"><div className="project-toolbar"><label><span className="visually-hidden">{s.mix.projectName}</span><input aria-label={s.mix.projectName} value={store.project?.name ?? ''} placeholder={s.mix.title} disabled={!store.project} maxLength={200} onChange={event => store.edit(project => ({ ...project, name: event.target.value }))} /></label><div className="project-actions"><span className={`save-status ${store.saveStatus === 'error' ? 'is-error' : ''}`} role="status">{store.saveStatus === 'saved' ? s.mix.saved : store.saveStatus === 'saving' ? s.mix.saving : s.mix.unsaved}</span><button className="button" disabled={!store.past.length} onClick={store.undo}>{s.mix.undo}</button><button className="button" disabled={!store.future.length} onClick={store.redo}>{s.mix.redo}</button><button className="icon-button" aria-label={s.mix.shortcuts} onClick={() => setHelpOpen(true)}>?</button></div></div>
      {store.error && <div className="library-connection" role="alert"><p>{store.error}</p><button className="text-button" onClick={() => void store.load()}>{s.library.tryAgain}</button></div>}
      {store.saveStatus === 'error' && <div className="library-connection" role="alert"><p>{s.mix.saveFailed}</p><button className="text-button" onClick={() => void flushSave().catch(() => {})}>{s.mix.retrySave}</button></div>}
      <div className="mix-workspace"><Library library={library} chooseFiles={chooseFiles} compact onAdd={store.addTrack} /><div className="editing-column">{store.loading ? <p role="status">{s.mix.loading}</p> : <><ClipEditor clip={selected} /><MixList /></>}</div></div>
    </main> : <main className="main-layout"><SetupPanel /><aside className="roadmap"><h2>{s.progressTitle}</h2><p className="roadmap-intro">{s.progressDescription}</p><ol>{s.steps.map((step, index) => <li key={step.name}><span className="step-number" aria-hidden="true">{index + 1}</span><div><h3>{step.name}</h3><p>{step.detail}</p></div></li>)}</ol><p className="roadmap-note">{s.offline}</p></aside></main>}
    {panel === 'setup' && (library.upload || library.uploadError || importing > 0) && <div className="global-import-notice" role="status"><p>{library.uploadError ?? (library.upload ? s.library.uploading(library.upload.count) : s.library.importingCount(importing))}</p><button className="text-button" type="button" onClick={() => setPanel('mix')}>{s.library.viewLibrary}</button></div>}
    <footer className="app-footer"><span className="local-label"><span className="local-dot" />{s.local}</span><span>{s.footer}</span></footer>
    {exportOpen && <ExportDialog onClose={() => setExportOpen(false)} />}
    {helpOpen && <Modal titleId="shortcut-title" onClose={() => setHelpOpen(false)}><div className="modal-heading"><h2 id="shortcut-title">{s.mix.shortcuts}</h2><button className="text-button" onClick={() => setHelpOpen(false)}>{s.mix.close}</button></div><dl className="keyboard-help">{[[s.mix.space, s.mix.playPauseHelp], ['I', s.mix.setStart], ['O', s.mix.setEnd], ['← / →', s.mix.seek], ['P', s.mix.playSelection], ['Ctrl+Z / Ctrl+Shift+Z', s.mix.undoHelp], ['Delete', s.mix.deleteHelp]].map(([key, description]) => <div key={key}><dt><kbd>{key}</kbd></dt><dd>{description}</dd></div>)}</dl></Modal>}
  </div>;
}
