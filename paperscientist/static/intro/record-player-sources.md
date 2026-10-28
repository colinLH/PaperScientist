# Interactive record collection — 2026-10-28

## Turntable image

`textures/record-player-walnut.png` is an original asset generated with the built-in image generation tool, then copied unchanged into this project. It is 1402 × 1122 RGBA (2,506,364 bytes), with transparent background. The moving metallic tonearm is a separate CSS layer. Four players share this one image and request it only after the first selection. This is a photorealistic generated product illustration, not a photograph of a commercial device.

Final generation prompt:

> Create one production-ready photorealistic product cutout for a website: a premium, real physical walnut-wood record player, precisely overhead orthographic top-down photography, camera pointing straight down, NO perspective tilt. Landscape asset roughly 5:4 aspect ratio. The whole turntable is centered with about 4 percent transparent padding. A rectangular solid warm dark walnut plinth with subtly rounded corners, realistic natural wood grain, polished beveled edge, very thin visible dark side edge on bottom, realistic studio lighting and small contact shadow. Black rubber circular platter with fine concentric grooves and brushed aluminium rim, EMPTY, no record: platter center exactly at 40 percent of entire image width and 49 percent of image height, platter diameter 62 percent of image width. Small silver spindle at exact platter center. At top right, a small brushed-silver circular tonearm pivot centered around 82 percent width, 25 percent height, but NO tonearm shaft attached (the website adds a moving tonearm separately). Small machined silver power dial and a tiny amber indicator at bottom right. NO text, NO logo, NO watermark, NO cables, NO dust cover, NO background surface. Genuine high-end product photograph, tactile real physical materials and precise machining, not painting, not illustration, not cartoon, not plastic CGI. Keep the platter perfectly circular for overlaying the separately animated record. Transparent alpha background.

## Music

All fifteen compositions are by [Scott Buckley](https://www.scottbuckley.com.au/library/), used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Each title in the website's music credits links to its official library page. [audio/records/credits.json](audio/records/credits.json) records the exact source URL, license, original/output SHA-256 and file size for every composition.

The first solo uses pastoral piano (Hiraeth), the second reflective orchestral music (Solace), the third intimate piano (Echoes Of Home), and the fourth cosmic ambient music (Aurora). Every unordered subset maps to its own composition through `record-score.mjs`. For example 1+2+4 selects Convergence and all four select Starfire. The selections are licensed existing compositions, not newly composed arrangements of the individual tracks.

Full-length audio is transcoded to Opus at 80 kbps VBR, with no cuts; playback applies volume and a 380 ms crossfade. Combined packaged audio is 49,607,745 bytes. It is **not** preloaded as a set: there is normally one record audio decoder, at most two during crossfade. Earlier fading sources are evicted during rapid clicks. The preparation script downloads from official pages, verifies the attribution license, writes provenance, and requires an explicit FFmpeg path. Source MP3 caches stay outside the repository.

## Interaction and resource budget

All four records begin stationary. A reversible spring preserves velocity during rapid clicks; the record lifts and settles onto the platter before it rotates. The tonearm follows the placement. Returning a record eases its rotation back to the gallery orientation. The decorative turn speed is 24 degrees/second, not a physical 33⅓ RPM simulation. A selected set retains separate playback progress in browser local storage across deselection and reload; clearing browser site data clears these saved positions.

Connections follow sorted disc indices. Neighboring records use direct links; skipped records use a lower curved bypass. Notes travel left to right at 34 pixels/second, use four alternating glyphs, and are capped at 128. Link geometry is cached. One shared effects canvas is capped at approximately 1.4 million pixels (rounding can add a few pixels), without adding a WebGL context or independent animation loop.

The first chapter uses the existing 30 FPS paint budget. Covered background drawing is suspended. Once every record has returned and pointer motion settles, the animation loop stops until the next interaction. Leaving the chapter releases record audio after the crossfade and stops record animation; returning resumes the selected composition. Hidden pages suspend sound and animation. Reduced-motion mode retains immediate selection and playback but suppresses animated placement, spinning and traveling notes.

## Rechecking performance

`/welcome?profile=1` adds local diagnostics to the existing frame loop. `/welcome?profile=motion` additionally enables normal motion explicitly for testing a preview browser configured to reduce motion. Neither changes browser or operating-system preferences. Normal `/welcome` visits create no diagnostic panel, observers or timers.

The panel reports recent intervals (up to 600 paints) and JavaScript paint duration; it excludes deliberate idle gaps. `heapMB` is Chrome's JavaScript heap estimate, **not** total browser, decoder or GPU memory. Frame and drawing time do not measure GPU utilization. Hidden or background browsers may throttle rendering, so compare visible foreground runs. Desktop and phone-sized viewport checks do not substitute for physical low-end devices.
