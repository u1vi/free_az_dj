import { afterEach, expect, it, vi } from 'vitest';
import { api } from './project';

afterEach(() => vi.unstubAllGlobals());
it('reads a playlist choice response without queuing unchecked entries', async () => {
  const result = { jobs: [], playlist: [{ url: 'https://www.youtube.com/watch?v=abcdefghijk', title: 'Song', duration_s: 180 }] };
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(result)));
  vi.stubGlobal('fetch', fetch);
  expect(await api('/api/tracks/youtube', { method: 'POST', body: JSON.stringify({ url: 'https://www.youtube.com/playlist?list=PLtest' }) })).toEqual(result);
  expect(fetch).toHaveBeenCalledTimes(1);
});
it('preserves the backend YouTube recovery message', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'This video is private or unavailable.' }), { status: 400 })));
  await expect(api('/api/tracks/youtube')).rejects.toThrow('This video is private or unavailable.');
});
