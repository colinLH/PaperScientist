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
            self.assertEqual(c.get('/intro-assets/../../config.py').status_code, 404)
