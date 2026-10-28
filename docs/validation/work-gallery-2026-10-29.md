# Work gallery density and 36 projects — 2026-10-29

## Change

- 36 distinct official research project pages, each with a different author-hosted demonstration video. Original 12 projects retained; 24 added across rendering, generation, editing and robotics.
- Alternating lower/upper rails now show four substantial curtains; at most five including edge entrants on desktop and two on compact screens. Same-rail curtains never overlap. Large viewport previews retain a landscape aspect ratio instead of stretching vertically.
- Preserved reversible WORK camera path, empty entrance/exit buffer, and one-third-viewport wheel distance.
- Compact native project picker plus previous/next controls replaces the 12-button strip.
- At most two video sources and five poster sources attached; offscreen media unloaded, hidden card transforms not updated, stationary Work canvas uses the existing loop's idle state. No additional continuous animation loop.

## Verification

- Node: 90/90 intro tests, including 13 Work tests. Geometry sampled over 1,001 positions at 390x844, 680x380, 1280x720, 2160x1440 and 3840x2160; no overlap, bounded visibility, forward/reverse consistency and exact one-third wheel distance.
- Python: 2/2 intro page/resource route tests. `git diff --check` passed.
- All 36 official project URLs and 36 video URLs returned HTTP 200/206. All 34 remote posters returned image responses; two 640 px local preview frames are attributed in work-sources.md. Initial transient TLS failures were retried; NeRF's stale GCS link was replaced with the alternative host linked by its official page.
- Browser: project picker reached entries 01, 18, 36 and 06; final item disables Next. These jumps retained at most five poster sources and two video sources. Pause removed all video sources; leaving Work removed all video and poster sources. Actual playback observed for Text2Room, Instruct-NeRF2NeRF, DragGAN, Diffusion Policy, NeRF and Dynamic 3D Gaussians.
- Browser layouts: desktop 2157x1243; narrow 390x844 (document width and scroll width both 390, two disjoint curtains); UHD 3840x2160 (five including partial edges, two videos, five posters, approximately 998x666 landscape cards).
- Nine runtime files (including two small JPEGs and provenance) SHA-256 matched the live E:/agent checkout.

## Limits

- External authors control media availability and autoplay/codec behavior varies by browser. HTTP range validation is not a full playback audit of all 36 videos; the original-site link and explicit unavailable fallback remain.
- Browser profiling was throttled around 1–2 frames/s in this environment. The sampled Work JavaScript draw cost was low (one settled-scroll sample p95 2.6 ms), but that is not an end-user FPS result. No low-end GPU or native GPU-memory benchmark was performed. DOM resource caps do not force browser HTTP-cache eviction.
- No iframe/site bundle, downloaded research data or credentials included. The only local media additions are two attributed demonstration stills (about 59 KB combined).
