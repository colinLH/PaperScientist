import asyncio
import base64
import io
import json
import socket

import httpx
from PIL import Image
from pypdf import PdfReader
import pytest

from paperscientist import figure_forge, micu_images
from paperscientist.config import Settings
from paperscientist.store import Store


def mock_server(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(micu_images.network, 'client_options', lambda: {'transport': transport, 'trust_env': False})


def png():
    buffer = io.BytesIO()
    Image.new('RGB', (200, 160), 'teal').save(buffer, 'PNG')
    return buffer.getvalue()


def test_chat_to_image_endpoint_registers_an_illustration(tmp_path, monkeypatch):
    image = png()
    store = Store(tmp_path)
    store.session('paper')
    cfg = Settings(credentials={'MICUAPI_API_KEY': 'unit-test-credential'})
    spec = {'type': 'illustration', 'prompt': 'Show a concept.', 'size': [3, 2], 'private_note': 'archive only'}
    store.file('paper', 'spec.json').write_text(json.dumps(spec))
    monkeypatch.setattr(figure_forge, 'search_references', lambda _: {'available': False})
    requests = []
    def server(request):
        requests.append(request)
        assert request.headers['Authorization'] == 'Bearer unit-test-credential'
        payload = json.loads(request.content)
        assert payload['model'] == cfg.image_model
        assert 'archive only' not in request.content.decode()
        if str(request.url) == micu_images.CHAT_ENDPOINT:
            assert 'Show a concept.' in payload['messages'][0]['content']
            return httpx.Response(404, json={'error': {'message': 'Unknown endpoint. (request id: xyz)'}})
        assert str(request.url) == micu_images.IMAGE_ENDPOINT
        assert payload['prompt'] == json.loads(requests[0].content)['messages'][0]['content']
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image).decode()}]})
    mock_server(monkeypatch, server)

    result = asyncio.run(figure_forge.create_agent_figure(store, 'paper', 'spec.json', 'figure', cfg, asyncio.Lock()))
    folder = store.workspace('paper') / result['directory']
    assert len(requests) == 2
    assert {p['kind'] for p in result['artifacts']} == {'figure', 'figure_source'}
    assert result['contract']['image_generation']['endpoint'] == micu_images.IMAGE_ENDPOINT
    assert 'unit-test-credential' not in json.dumps(result)
    assert result['contract']['panels'] == []
    assert Image.open(folder / 'figure.png').size == (200, 160)
    page = PdfReader(folder / 'figure.pdf').pages[0]
    assert tuple(map(float, (page.mediabox.width, page.mediabox.height))) == (216, 144)


def test_markdown_image_download_and_redirect_receive_no_credentials(monkeypatch):
    image = png()
    cfg = Settings(credentials={'MICUAPI_API_KEY': 'unit-test-credential'})
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *_: [(None, None, None, None, ('93.184.216.34', 443))])
    paths = []
    def server(request):
        paths.append(request.url.path)
        if request.url.host == 'www.micuapi.ai':
            message = {'content': 'Here is your figure. ![diagram](https://images.example/get)'}
            return httpx.Response(200, json={'choices': [{'message': message}]})
        assert 'authorization' not in request.headers
        if request.url.path == '/get':
            return httpx.Response(302, headers={'Location': 'https://cdn.example/image.png'})
        return httpx.Response(200, content=image)
    mock_server(monkeypatch, server)
    assert asyncio.run(micu_images.generate(cfg, 'diagram')) == (image, micu_images.CHAT_ENDPOINT)
    assert paths == ['/v1/chat/completions', '/get', '/image.png']


@pytest.mark.parametrize('status,body', [
    (302, {}),
    (429, {'error': {'message': 'unit-test-credential'}}),
    (404, {'error': {'message': 'Model not found'}}),
    (200, {'choices': [{'message': {'content': 'This is a description only'}}]}),
    (200, {'choices': [{'message': {'images': [{'image_url': {'url': 'http://127.0.0.1/'}}]}}]}),
])
def test_no_retry_on_ambiguous_or_unsupported_response(monkeypatch, status, body):
    seen = []
    def server(request):
        seen.append(request.url.path)
        return httpx.Response(status, json=body, headers={'location': 'https://other.example/'})
    mock_server(monkeypatch, server)
    with pytest.raises(ValueError) as error:
        asyncio.run(micu_images.generate(Settings(credentials={'MICUAPI_API_KEY':'unit-test-credential'}), 'test'))
    assert 'unit-test-credential' not in str(error.value)
    assert seen == ['/v1/chat/completions']


def test_missing_key_and_invalid_pixels(tmp_path):
    with pytest.raises(ValueError, match='MICUAPI_API_KEY'):
        asyncio.run(micu_images.generate(Settings(), 'test'))
    with pytest.raises(ValueError, match='valid PNG'):
        micu_images.export_illustration(b'<html>expired</html>', [3, 2], tmp_path)
    assert not list(tmp_path.iterdir())
