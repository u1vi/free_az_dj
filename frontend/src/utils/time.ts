export function formatTime(seconds: number, precise = false): string {
  const ms = Math.max(0, Math.round(seconds * 1000));
  const minutes = Math.floor(ms / 60000);
  const remainder = Math.floor(ms / 1000) % 60;
  return precise ? `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}` : `${minutes}:${String(remainder).padStart(2, '0')}`;
}
export function parseTime(value: string): number | null {
  if (!/^\d+:\d{1,2}(?:\.\d{1,3})?$/.test(value.trim())) return null;
  const [minutes, seconds] = value.trim().split(':');
  if (Number(seconds) >= 60) return null;
  return Number(minutes) * 60 + Number(seconds);
}
export interface TimedClip { start_s: number; end_s: number; transition: string; transition_s: number }
export function timeline(clips: TimedClip[]) {
  const lengths = clips.map(clip => Math.max(0, clip.end_s - clip.start_s));
  const offsets: number[] = []; const transitions: number[] = []; const clamped: number[] = [];
  let current = 0;
  clips.forEach((clip, index) => {
    offsets.push(current); current += lengths[index];
    if (index === clips.length - 1) return;
    if (clip.transition === 'crossfade') {
      const overlap = Math.max(0, Math.min(clip.transition_s, lengths[index] / 2, lengths[index + 1] / 2));
      transitions.push(overlap); current -= overlap;
      if (overlap < clip.transition_s - 0.0005) clamped.push(index);
    } else if (clip.transition === 'gap') { const gap = Math.max(0, clip.transition_s); transitions.push(gap); current += gap; }
    else transitions.push(0);
  });
  return { lengths, offsets, transitions, clamped, total: current };
}
