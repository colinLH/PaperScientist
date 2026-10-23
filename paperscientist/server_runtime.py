"""Startup policy for the API-hosted model server (not research subprocesses)."""
import os


def configure_server_runtime():
    """Avoid loading optional local ML backends just to use cloud chat APIs.

    Some LangChain versions eagerly import Transformers' tokenizer helper, which
    otherwise imports installed Torch/CUDA libraries. Explicit deployment choices
    win. run_python uses its own allowlisted environment and can still use Torch.
    """
    if os.environ.get('PS_LIGHTWEIGHT_SERVER', 'true').lower() in {'0', 'false', 'off'}:
        return
    for name in ('USE_TORCH', 'USE_TF', 'USE_FLAX'):
        os.environ.setdefault(name, '0')
