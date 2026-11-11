import { useRef, useState, type DragEvent } from 'react';
import { strings as s } from '../strings';

interface Props {
  chooseFiles: () => void;
  importFiles: (files: File[]) => Promise<void>;
  upload: { count: number; progress: number } | null;
  error: string | null;
}

export function ImportBar({ chooseFiles, importFiles, upload, error }: Props) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const drop = (event: DragEvent) => {
    event.preventDefault(); depth.current = 0; setDragging(false);
    void importFiles(Array.from(event.dataTransfer.files));
  };
  return <div className="import-area">
    <div className={`drop-zone ${dragging ? 'is-dragging' : ''}`} onDragEnter={event => { event.preventDefault(); depth.current++; setDragging(true); }} onDragOver={event => event.preventDefault()} onDragLeave={event => { event.preventDefault(); depth.current--; if (depth.current === 0) setDragging(false); }} onDrop={drop}>
      <svg className="drop-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 16V3m-4 4 4-4 4 4M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" /></svg>
      <div className="drop-copy"><h2>{dragging ? s.library.dropNow : s.library.dropTitle}</h2><p>{s.library.formats}</p></div>
      <button className="button" type="button" onClick={chooseFiles} disabled={Boolean(upload)}>{s.library.chooseFiles}</button>
    </div>
    {upload && <div className="upload-progress" role="status" aria-live="polite"><div><span>{upload.progress < 1 ? s.library.uploading(upload.count) : s.library.finishingUpload}</span><span>{Math.round(upload.progress * 100)}%</span></div><progress max="1" value={upload.progress} aria-label={s.library.uploadProgress} /></div>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
