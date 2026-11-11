import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../api/library';
import { strings as s } from '../strings';

export function useLibrary() {
  const [tracks, setTracks] = useState<api.Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ count: number; progress: number } | null>(null);
  const mounted = useRef(true);
  const uploadLock = useRef(false);
  const sequence = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++sequence.current;
    try {
      const result = await api.listTracks();
      if (mounted.current && request === sequence.current) { setTracks(result); setError(null); }
    } catch (error) {
      if (mounted.current && request === sequence.current) setError(error instanceof Error ? error.message : s.library.requestFailed);
    } finally { if (mounted.current) setLoading(false); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    let active = true;
    let timer: number | undefined;
    const poll = async () => { await refresh(); if (active) timer = window.setTimeout(() => void poll(), 1000); };
    void poll();
    return () => { active = false; mounted.current = false; window.clearTimeout(timer); };
  }, [refresh]);
  const importFiles = useCallback(async (files: File[]) => {
    if (!files.length) return;
    if (uploadLock.current) { setUploadError(s.library.uploadBusy); return; }
    uploadLock.current = true; setUploadError(null); setUpload({ count: files.length, progress: 0 });
    try {
      await api.uploadTracks(files, progress => { if (mounted.current) setUpload({ count: files.length, progress }); });
      await refresh();
    } catch (error) { if (mounted.current) setUploadError(error instanceof Error ? error.message : s.library.uploadFailed); }
    finally { uploadLock.current = false; if (mounted.current) setUpload(null); }
  }, [refresh]);
  const rename = useCallback(async (id: string, title: string) => { await api.renameTrack(id, title); await refresh(); }, [refresh]);
  const remove = useCallback(async (id: string) => { await api.removeTrack(id); setTracks(current => current.filter(track => track.id !== id)); await refresh(); }, [refresh]);
  const retry = useCallback(async (id: string) => { await api.retryTrack(id); await refresh(); }, [refresh]);
  return { tracks, loading, error, upload, uploadError, refresh, importFiles, rename, remove, retry };
}

export type LibraryState = ReturnType<typeof useLibrary>;
