# Global cities globe

Visual reference requested by the user: [如何用 Three.js 做 3D 地球](https://juejin.cn/post/7474078374319980544), VincentFHR, 2025-02-22. Independently implemented sphere, atmospheric rim, moving scan, cloud veil, city pins/ripples, intercontinental arcs, satellites and click/drag interaction. No article source code or image assets copied.

## Geographic data

Natural Earth **v5.1.2**, [public domain](https://www.naturalearthdata.com/about/terms-of-use/), from the Natural Earth maintainer's repository:

- [110m land](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson). SHA-256 `9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9`.
- [110m populated places](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_populated_places_simple.geojson). SHA-256 `0dbd25c9ad8bd797ddf164b067f563be5c16be2c002254eb594862377963f9dc`.

`earth-data.mjs` retains 127 land polygons (coordinates rounded to four decimal places) and a curated selection of 41 major cities across six inhabited continents. City coordinates are unchanged from the source. Chinese names are display translations. This is a geographically distributed selection, not a population ranking or exhaustive city list. Only land/coastline polygons are drawn; administrative boundaries are not included.

The map mask is generated locally from these vectors once at 2048×1024; no external textures, APIs or CDN are needed at runtime. The globe and markers share the same longitude convention and rotation. Routes are illustrative connections, not actual flights, research collaborations or traffic measurements. Clouds and satellite motion are decorative, not weather or orbital data.

## Motion and resource budget

The existing welcome clock drives the globe at 0.075 rad/s (about 84 seconds per revolution). Dragging adds a smoothed rotation offset; choosing a city rotates by the shortest path to its actual location while automatic rotation continues. Reduced-motion mode freezes ambient movement and retains direct selection. Keyboard and vertical chapter gestures remain available.

One additional WebGL canvas is capped at 2.2 million pixels and DPR 1.5. The canvas only renders during the second scene's reversible fade interval. Cities, light pillars, ripple rings and moving signals use instanced drawing; normal views use about 23–24 draw calls. Route geometry is rebuilt only on city selection and disposed before replacement. Page exit disposes buffers, geometries, materials, textures and the renderer; hidden tabs use the existing stopped clock. On WebGL initialization/context failure, the existing projected city fallback remains available. This fallback does not provide the detailed geographic surface or WebGL effects.

At most eight labels appear on desktop and four on phones, with front-side visibility and rectangle collision checks. All cities are available through the accessible selector even when their labels are hidden behind the sphere. The cap limits rendered pixels; it is not a claim of measured low-end or 4K frame rate.
