import { describe, expect, it } from 'vitest';
import { formatTime, parseTime, timeline } from './time';

describe('precise trim times', () => {
  it('round-trips millisecond values without losing 50ms edits', () => {
    for (const time of [0, 0.05, 1.125, 59.999, 60.001, 3600.025]) expect(parseTime(formatTime(time, true))).toBeCloseTo(time, 3);
    expect(formatTime(59.9999, true)).toBe('01:00.000');
    expect(formatTime(7325)).toBe('122:05');
  });
  it('rejects malformed or impossible minute fields', () => {
    for (const value of ['1:60', '-1:20', 'abc', '2', '1:22.3456', '1:999']) expect(parseTime(value)).toBeNull();
    expect(parseTime('02:12.5')).toBe(132.5);
  });
});

describe('mix timing', () => {
  const clip = (length: number, transition = 'crossfade', transition_s = 4) => ({ start_s: 0, end_s: length, transition, transition_s });
  it('includes overlaps, gaps and hard cuts in song offsets', () => {
    const result = timeline([clip(100), clip(60, 'gap', 2), clip(40, 'cut'), clip(20)]);
    expect(result.offsets).toEqual([0, 96, 158, 198]);
    expect(result.total).toBe(218);
  });
  it('clamps crossfades to half of both adjacent clips', () => {
    const result = timeline([clip(2, 'crossfade', 10), clip(0.4, 'crossfade', 10), clip(4)]);
    expect(result.transitions).toEqual([0.2, 0.2]);
    expect(result.clamped).toEqual([0, 1]);
    expect(result.total).toBeCloseTo(6);
  });
  it('handles an empty mix and ignores the final transition', () => {
    expect(timeline([]).total).toBe(0);
    expect(timeline([clip(8, 'gap', 20)]).total).toBe(8);
  });
});
