# Record-player validation — 2026-10-28 (Asia/Shanghai)

## Automated checks

85 Node tests across the intro modules and 2 Python page/resource-route tests pass. New cases cover all 15 unordered combinations, unique audio hashes and attribution, idle/deploy/spin/return choreography, reversal continuity, narrow/desktop/4K geometry, curved bypass clearance, independent progress, rapid switching with at most two decoders, stale play promises, retry after failure, browser timer binding, and suspending the fully covered canvas. All 15 Opus files support HTTP Range requests and the audio/ogg MIME type. JavaScript syntax and whitespace checks pass.

## Actual browser checks

Using the visible in-app Chromium browser on this workstation:

- Initial records are stationary with no record audio element. Settled first chapter reports `renderState=idle`.
- Clicking creates the photographed-style walnut machine, seats and rotates the record, and moves the tonearm. The third record has the new English title.
- Selection 1+2+4 produces Convergence and links `1-2:straight,2-4:curve`. Selecting all four produces Starfire and three direct links.
- Leaving 1+2+4 at approximately 89.88 seconds, then selecting it again, resumes near 89.90 seconds. Reloading near 156.94 seconds and selecting in reverse order (4,2,1) resumes near 156.97 seconds. Compositions loop at their natural ends.
- Navigating to the garden removes record audio after the crossfade; returning resumes the prior selection. All records returned to the gallery leave zero record decoders and stop the animation loop after settling.
- 3840×2160 and 390×844 viewports have no document horizontal overflow. Resize repositions machines and routes. Browser logs contain no warnings/errors in the final run.

## Bounded performance samples

The opt-in diagnostic observes the existing render loop rather than adding a second loop. These are foreground, normal-motion samples; the IAB default reduced-motion preference was explicitly overridden only with `?profile=motion`.

| Viewport / selection | Elapsed seconds | Paint samples | Recent paint FPS | Frame interval p95 | JS paint cost p95 | Recent intervals >66.7 ms | JS heap |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1280×720 / four records | 133.8 | 4012 | 30.0 | 37.6 ms | 0.6 ms | 0 | 12.1 MB |
| 1280×720 / 1+2+4, curved bypass | 88.7 | 2663 | 30.0 | 37.6 ms | 0.7 ms | 0 | 12.6 MB |
| 3840×2160 / four records | 106.1 | 3183 | 30.0 | 37.6 ms | 0.6 ms | 0 | 13.2 MB |

FPS, percentiles and long-frame counts use the recent window (up to 600 paints, approximately 20 seconds), not every frame of the entire elapsed run. Deliberate idle gaps are excluded. One record decoder remains after each crossfade; four-record 4K rendering uses 28 notes and an effects canvas of 1,400,070 pixels. At most two record decoders exist while changing composition. Existing background-scene audio is separately paused while records play.

No obvious stutter was observed in these foreground samples. JavaScript paint cost excludes compositor/GPU work and is not end-to-end latency; JS heap excludes textures, media buffers and GPU memory. Hidden Chrome throttled to about 1 FPS during an earlier check, so that run is not used as a performance result. Phone checks use a viewport override, not a physical device. No low-end-device or OS GPU-utilization benchmark was performed.

The new turntable shares one lazy-loaded 2.51 MB image. Music totals 49.61 MB on disk but only selected and fading tracks load; the page does not decode or fetch all fifteen compositions on entry. Empty selection stops rendering once the view settles. Offscreen scenes suspend drawing, and page disposal releases record audio and visual resources.
