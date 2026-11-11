export type ToolId = 'ffmpeg' | 'ffprobe' | 'yt-dlp' | 'deno';

export interface ToolCheck {
  id: ToolId;
  version: string | null;
  status: 'ready' | 'missing' | 'outdated' | 'error';
  message: string | null;
}

export interface SystemCheck {
  ready: boolean;
  tools: ToolCheck[];
  filter_graph_option: '-/filter_complex' | '-filter_complex_script' | null;
}

export async function getSystemCheck(signal: AbortSignal): Promise<SystemCheck> {
  const response = await fetch('/api/system/check', { signal, cache: 'no-store' });
  if (!response.ok) throw new Error(`System check failed (${response.status})`);
  return response.json() as Promise<SystemCheck>;
}
