import {clamp, smooth} from './motion.mjs';
import {portalEase} from './work-layout.mjs';

// The artwork keeps its established camera route. Extra travel beats give the
// warp and the Work entrance/gallery/exit room without skipping either scene.
export const LAST_STOP = 10;
export const chapterStops = [0, 1, 2, 3, 4, 6, LAST_STOP];
export function journeyFrame(value) {
  const p = clamp(value, 0, LAST_STOP);
  const landscape = p <= 2 ? p : p < 4 ? 2 + (p - 2) / 2 : p < 9 ? 3 : 3 + (p - 9) * 2;
  const warp = smooth((p - 2.25) / .55) * (1 - smooth((p - 3.2) / .65));
  const work = smooth((p - 4.25) / .65) * (1 - smooth((p - 9.25) / .75));
  const aperture = portalEase(p - 5) * (1 - portalEase(p - 8));
  const chapter = p < 2.5 ? Math.round(p) : p < 3.5 ? 3 : p < 4.65 ? 4 : p < 9.6 ? 5 : 6;
  return {p, landscape, warp, work, aperture, chapter,
    star: Math.max(0, 1 - Math.abs(p - 4) * 2),
    copy: chapter === 5 ? 0 : 1 - Math.min(1, Math.abs(p - Math.round(p)) * 2.3),
    music: p <= 2 ? p : p < 4 ? 2 + (p - 2) / 2 : p < 9 ? 3 + (p - 4) / 5 : 4 + (p - 9),
    gallery: p >= 5.85 && p <= 8.15,
    workProgress:clamp((p-6)/2,0,1)};
}

export function warpDepth(seed, travel) {
  // Periodic analytical depth: reversing the camera retraces the same field.
  return .055 + (((seed - travel) % 1 + 1) % 1) * .945;
}
