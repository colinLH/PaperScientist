import os
import unittest
from unittest.mock import patch

from paperscientist.server_runtime import configure_server_runtime


class ServerRuntimeTests(unittest.TestCase):
    def test_default_avoids_unused_ml_backends(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_server_runtime()
            self.assertEqual([os.environ[k] for k in ('USE_TORCH', 'USE_TF', 'USE_FLAX')], ['0'] * 3)

    def test_explicit_deployment_settings_are_preserved(self):
        with patch.dict(os.environ, {'USE_TORCH': '1'}, clear=True):
            configure_server_runtime()
            self.assertEqual(os.environ['USE_TORCH'], '1')
        with patch.dict(os.environ, {'PS_LIGHTWEIGHT_SERVER': 'false'}, clear=True):
            configure_server_runtime()
            self.assertNotIn('USE_TORCH', os.environ)
