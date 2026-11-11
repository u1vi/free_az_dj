export function StatusIcon({ ready }: { ready: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      {ready ? <path d="m8 12 3 3 5-6" /> : <><path d="M12 7v6" /><path d="M12 16h.01" /></>}
    </svg>
  );
}
