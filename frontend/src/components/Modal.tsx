import { useEffect, useRef, type ReactNode } from 'react';

export function Modal({ titleId, onClose, busy = false, children, className = '' }: { titleId: string; onClose: () => void; busy?: boolean; children: ReactNode; className?: string }) {
  const element = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = element.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={element} className={`modal ${className}`} aria-labelledby={titleId} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>{children}</dialog>;
}
