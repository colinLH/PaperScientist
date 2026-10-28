# Record hand, ensemble celebration and room validation — 2026-10-28

## Automated checks

88 Node intro tests and 2 Python intro/asset route tests pass. Added checks cover reach-before-lift, continuous reversal, hand withdrawal before spin, constant apparent hand size and rim contact at phone/desktop/4K geometry sizes, fixed firework budget, cooldown, cancellation before rendering, reduced motion, and audio-position migration. All fifteen licensed audio assets pass manifest SHA-256 checks. The new hand image/module and Hyperion range route return successfully. `git diff --check` passes.

## Observed browser behavior

Actual UI selection showed hand reach/place/remove, individual and full-set playback, three colored bursts, then automatic burst completion (`fireworks=false`, `sparks=0`). Hyperion's audio element was playing and its position advanced. The ivory listening-room backdrop and reused sleeve artwork were visually inspected. The final hand-size compensation passed geometry checks; a complete final visual sequence could not be recaptured before browser automation ended.

A foreground 1280×720 full-set run after style-write optimization reported 374.8 seconds / 11,242 paints, 30 paint FPS, frame interval p95 37.6 ms, JavaScript paint p95 1.1 ms and max 2.6 ms, zero intervals above 66.7 ms in the recent window, one record decoder and about 1.4 million effect pixels. Its 113 burst samples reported paint p95 1.2 ms and zero long intervals. JavaScript heap estimate was 13.3 MB. This sample preceded only the final constant-size hand compensation, which does not run after hands withdraw.

Later attempts ran in an obscured/background browser and reported intervals around one second. These are not presented as foreground performance results. Computer Use then stopped because it could not confidently identify the Windows browser URL for its safety checks; no further UI automation was attempted. The final 4K/phone visual and performance rerun was therefore **not completed**. Earlier feature validation is recorded separately in record-player-2026-10-28.md and is not counted as a fresh run for this revision.

## Limits and resource controls

Statistics use recent windows (up to 600 paints), not every frame of the whole elapsed run. JavaScript heap excludes audio buffers, decoded images and GPU memory; JavaScript drawing time is not GPU utilization. No real low-end device or physical-phone benchmark was performed. Hands use one shared, lazy 1.30 MB transparent image; fireworks last 3.8 seconds with 240 desktop / 120 narrow strokes and cannot accumulate; both share the existing clock. Static background decoration reuses existing art. Audio remains one decoder in steady state, at most two during transition. Reduced-motion and disposal behavior are checked automatically.
