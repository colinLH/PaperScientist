import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from paperscientist.intro import mount_intro


class IntroTests(unittest.TestCase):
    def test_intro_routes_keep_deep_links_and_audio_range_requests(self):
        app = FastAPI()
        mount_intro(app)
        @app.get('/')
        def workspace():
            return {'workspace': True}
        with TestClient(app) as c:
            self.assertEqual(c.get('/', follow_redirects=False).headers['location'], '/welcome')
            for query in ('workspace=1', 'session=abc', 'project=xyz'):
                self.assertEqual(c.get('/?'+query).json(), {'workspace': True})
            self.assertIn('开始我的研究', c.get('/welcome').text)
            r = c.get('/intro-assets/audio/hiraeth.mp3', headers={'range':'bytes=0-99'})
            self.assertEqual(r.status_code, 206)
            self.assertEqual(len(r.content), 100)
            for mask in range(1, 16):
                r = c.get(f'/intro-assets/audio/records/{mask:02}.opus', headers={'range': 'bytes=0-99'})
                self.assertEqual(r.status_code, 206)
                self.assertEqual(r.content[:4], b'OggS')
                self.assertIn('audio/ogg', r.headers['content-type'])
            for asset in ('record-player.mjs', 'record-audio.mjs', 'record-score.mjs', 'textures/record-player-walnut.png'):
                self.assertEqual(c.get('/intro-assets/' + asset).status_code, 200)
            # Browser workers and WASM must work from the same local origin,
            # without a CDN or frontend package manager at runtime.
            r = c.get('/intro-assets/vendor/mediapipe/wasm/vision_wasm_internal.wasm', headers={'range': 'bytes=0-3'})
            self.assertEqual(r.status_code, 206)
            self.assertEqual(r.content, b'\x00asm')
            self.assertIn('application/wasm', r.headers['content-type'])
            self.assertEqual(c.get('/intro-assets/hand-worker.js').status_code, 200)
            for asset in ('journey-map.mjs', 'gravity.mjs', 'cosmic-art.mjs', 'reference-art.mjs', 'garden-atmosphere.mjs', 'garden-pond.mjs', 'closing-landscape.mjs', 'prelude-interaction.mjs', 'earth-data.mjs', 'earth-geometry.mjs', 'earth-globe.mjs', 'constellation.js', 'warp.js', 'work.js', 'work-layout.mjs', 'paper-previews.mjs', 'immersive.css', 'work/atlas.svg', 'work/paper.svg', 'textures/disc-pagoda-4k.webp', 'textures/disc-watertown-4k.webp', 'textures/disc-pastoral.webp', 'textures/disc-milky-way-4k.webp', 'textures/garden-reference-4k.webp'):
                r = c.get('/intro-assets/' + asset)
                self.assertEqual(r.status_code, 200, asset)
                if asset.endswith('.svg'):
                    self.assertIn('image/svg+xml', r.headers['content-type'])
            self.assertEqual(c.get('/intro-assets/../../config.py').status_code, 404)

    def test_texture_mime_overrides_incorrect_windows_file_associations(self):
        import mimetypes
        from unittest.mock import patch

        with patch.dict(mimetypes.types_map, {'.webp': 'text/plain'}):
            app = FastAPI()
            mount_intro(app)
            with TestClient(app) as c:
                r = c.get('/intro-assets/textures/nebula-4k.webp', headers={'range': 'bytes=0-11'})
                self.assertEqual(r.status_code, 206)
                self.assertEqual(r.headers['content-type'], 'image/webp')
                self.assertEqual(r.content[:4], b'RIFF')
                self.assertEqual(r.content[8:12], b'WEBP')
