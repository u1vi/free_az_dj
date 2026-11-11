import { useCallback, useEffect, useRef, useState } from 'react';
import { getSystemCheck, type SystemCheck, type ToolCheck } from '../api/client';
import { StatusIcon } from './StatusIcon';
import { strings as s } from '../strings';

function DependencyRow({ tool }: { tool: ToolCheck }) {
  const text = s.tools[tool.id];
  const ready = tool.status === 'ready';
  return <li className="tool-row">
    <div className={ready ? 'tool-icon is-ready' : 'tool-icon is-error'}><StatusIcon ready={ready} /></div>
    <div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline gap-x-3 gap-y-1"><h3>{text.name}</h3><span className="tool-version">{tool.version ?? (tool.status === 'missing' ? s.notInstalled : s.versionUnavailable)}</span></div><p className="tool-purpose">{text.purpose}</p>{!ready && <p className="tool-recovery">{text.recovery}</p>}</div>
    <span className={ready ? 'status-label is-ready' : 'status-label is-error'}>{s[tool.status]}</span>
  </li>;
}

export function SetupPanel() {
  const [system, setSystem] = useState<SystemCheck | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const check = useCallback(async () => {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    const timeout = window.setTimeout(() => request.abort(), 12_000);
    setLoading(true); setError(false);
    try { const result = await getSystemCheck(request.signal); if (controller.current === request) setSystem(result); }
    catch { if (controller.current === request) setError(true); }
    finally { window.clearTimeout(timeout); if (controller.current === request) setLoading(false); }
  }, []);
  useEffect(() => { void check(); return () => { controller.current?.abort(); controller.current = null; }; }, [check]);
  const ready = system?.ready ?? false;
  const title = loading ? s.checking : error ? s.connectionError : ready ? s.allReady : s.needsAttention;
  const description = loading ? s.loadingDescription : error ? s.connectionRecovery : ready ? s.allReadyDescription : s.needsAttentionDescription;
  return <section aria-labelledby="setup-heading">
    <div className="section-heading"><div><h1 id="setup-heading">{s.setup}</h1><p>{s.setupDescription}</p></div><button type="button" onClick={() => void check()} disabled={loading}>{loading ? s.checking : s.checkAgain}</button></div>
    <div className={`check-summary ${!loading && (error || !ready) ? 'summary-warning' : ''}`} role="status" aria-live="polite">{!loading && <StatusIcon ready={!error && ready} />}<div><h2>{title}</h2><p>{description}</p></div></div>
    <div className="tool-list-wrapper" aria-busy={loading}>{system && !error ? <ul className="tool-list">{system.tools.map(tool => <DependencyRow key={tool.id} tool={tool} />)}</ul> : loading ? <div className="loading-placeholder">{s.loadingDescription}</div> : null}</div>
    <div className="setup-help"><h2>{s.setupHelp}</h2><p>{s.setupHelpDescription}</p></div>
  </section>;
}
