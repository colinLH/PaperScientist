# User-selected disc artwork — 2026-10-28

These three images were supplied by the user specifically for the welcome-page discs. The first delivery retained their native dimensions and colours. The later requested 4K replacement is described below; the source attachments and original delivery files remain unchanged.

| Asset | Position | Native size | Encoding |
| --- | --- | --- | --- |
| disc-pagoda.webp | Central disc (方向), user image 1 | 334 × 188 | Lossless WebP |
| disc-pastoral.webp | Far-left partial disc (观察), user image 2 | 4421 × 2500 | WebP quality 90, 2,732,000 bytes instead of the 20,794,506-byte PNG |
| disc-milky-way.webp | Far-right disc (探索), user image 3 | 547 × 365 | Lossless WebP |

The neighbouring left disc (文献) still uses the previous nebula texture. Cover cropping is applied by CSS within each circular disc. Original creator/licensing metadata was not supplied with the attachments.

## Requested 4K replacement

The supplied `figure1.jpg` was also only 334×188. The central and far-right disc images were reconstructed with the built-in image generation tool using their references, then super-resolved locally with Real-ESRGAN. They preserve the subjects and composition direction but contain reconstructed details, not recovered photographic evidence. The third chapter's existing garden painting was super-resolved directly without regeneration or layout redesign.

- `disc-pagoda-4k.webp`: 3840×2160; central disc.
- `disc-milky-way-4k.webp`: 3840×2560; far-right disc, retaining 3:2 framing.
- `garden-reference-4k.webp`: 3840×2160; third chapter.

All three are enhanced 4K exports, not native 4K captures. Full prompts: `4k-artwork-prompts.md`. Dimensions, hashes and model settings: `artwork-4k.json`. No upscaling model runs in the browser.

## Water-town disc and closing landscape revision

The later two-image request replaces the central disc again, this time with the user's second image: a pink water-town painting with boats and an arch bridge. `disc-watertown-4k.webp` is a direct Real-ESRGAN x4 enhancement of that 1000×561 attachment, fitted to 3840×2160 and encoded as WebP quality 96 (1,867,024 bytes). Its composition and source marks are retained; it has not been redrawn. This is an enhanced export, not native 4K artwork. Source/output hashes and processing details are in `disc-watertown-4k.json`.

The first image in that request has SHA-256 `222d5eac12623526c971b535821442fc764b64d486a460d038af2b61a4b29f3d` and is byte-identical to the earlier 1672×941 pagoda reconstruction. The final chapter therefore reuses its existing 3840×2160 derivative, `disc-pagoda-4k.webp`, without a duplicate asset or another regeneration. The far-left pastoral, neighbouring nebula and far-right Milky Way images keep their existing files.
