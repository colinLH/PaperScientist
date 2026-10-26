# Welcome Work gallery

Motion reference: the Work chapter of [Wodniack](https://wodniack.dev/), checked against the user's recording: bowed red corridor, vertical WORK capsule, concave repeated letter wall, then the reverse capsule exit. This is an independent implementation. No website source, proprietary fonts or recordings are bundled.

The gallery uses two parallel horizontal rails, three persistent cards each. Wheel distance drives both the rails and the cylindrical letter wall. Reversing scroll retraces the same positions; stopping preserves them indefinitely. Cards wrap only outside the viewport. Touch drags also scrub, while keyboard chapter changes are instantaneous. Entrance/exit inertia cannot accidentally traverse the whole gallery. The existing capsule curve concentrates the opening/closing movement, and the critically damped spring is faster in Work without resetting velocity when reversed.

The six previews link to official research project sites. Each mini page uses the project's title, venue, cover and a muted, looping demonstration video. These are official project media previews, not live embedded websites. Third-party websites, scripts and tracking code are not executed inside the gallery. Media stay on their authors' servers and retain their original ownership:

- [Nerfies](https://nerfies.github.io/)
- [HyperNeRF](https://hypernerf.github.io/)
- [DreamFusion](https://dreamfusion3d.github.io/)
- [Zip-NeRF](https://jonbarron.info/zipnerf/) (cover from the author's home page; the project page's OG cover currently returns 404)
- [Mip-NeRF 360](https://jonbarron.info/mipnerf360/)
- [Ref-NeRF](https://dorverbin.github.io/refnerf/)

Only the central preview in each row plays. Other cards show covers. Leaving the scene, opening the credits dialog, hiding the tab, or pausing previews unloads video sources. Late playback promises cannot restart an inactive card or pause a newly reactivated card. Network failures and autoplay denial fall back to the cover/source link; the pause/play control allows an explicit retry. Reduced motion leaves previews static unless the user enables playback. Public media URLs require network access and may change independently of this repository.

The letter wall is one 2D canvas using a cached glyph sprite instead of many transformed SVG nodes. Its drawing buffer is capped near 2.2 million pixels. Work targets 60 scene updates per second during movement and stops repainting when settled; videos use their own browser decoder clocks. No extra WebGL context or postprocessing framebuffer is created. The original six SVG illustrations remain as bundled artwork, but are not used by the new paper previews.

The seven chapters keep their eleven navigation stops: valley → literature → observatory → warp → nebula → Work capsule → gallery (continuous scroll between stops 6 and 8) → capsule exit → dawn. The original nebula, meteors, camera, hands and music remain in their established renderer. The warp retains 400 projected stars, five speed levels and its 2.6-million-pixel cap.
