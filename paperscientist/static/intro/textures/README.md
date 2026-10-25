# Nebula textures

`nebula-reference.png` is the unchanged 1024 × 503 reference supplied by the
project owner on October 24, 2026. `nebula-hd.png` is a 1672 × 941 reference-guided
reconstruction made with the built-in image generator; its exact prompt is in
`nebula-hd-prompt.txt`.

The page uses **`nebula-4k.webp`, 3840 × 2160**, enhanced locally with the owner's
approval using [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), the
`realesrgan-x4plus` model, and the official Windows ncnn Vulkan 20220424 release.
The 4× output (6688 × 3764) is center-fitted to UHD with Pillow's Lanczos filter,
then encoded as WebP quality 96, method 6. This is super-resolved artwork, **not a
native 4K astronomical photograph**. SHA-256 hashes and build settings are in
`nebula-4k.json`; the model and executable are offline build tools, not runtime
dependencies or production assets.

Rebuild with the official portable executable and model directory:

```text
realesrgan-ncnn-vulkan.exe -i nebula-hd.png -o nebula-sr-4x.png -m models -n realesrgan-x4plus -s 4 -t 256 -j 1:1:1
```

```python
from PIL import Image, ImageOps
image = Image.open('nebula-sr-4x.png').convert('RGB')
ImageOps.fit(image, (3840, 2160), method=Image.Resampling.LANCZOS).save(
    'nebula-4k.webp', quality=96, method=6)
```

The sky shader uses an aspect-preserving crop and small pointer parallax; the
pre-existing meteor and star-twinkle shaders are unchanged. The settled fourth
chapter renders at native display density up to 8.29 million pixels (UHD at 16:9).
Transitions and the other chapters keep the 1.4 million pixel budget. Film grain
and haze overlays are disabled in chapter four to preserve fine image detail.

The procedural nebula remains as a fallback if the image cannot load.
