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
