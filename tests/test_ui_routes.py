"""Regression tests for public React route migration."""

import re

import pytest


@pytest.mark.api
def test_public_root_serves_react(flask_client):
    response = flask_client.get('/')
    assert response.status_code == 200
    assert response.content_type.startswith('text/html')
    assert b'<div id="root"></div>' in response.data


@pytest.mark.api
def test_legacy_app_paths_redirect_to_root(flask_client):
    for path in ('/app', '/app/', '/app2', '/app2/'):
        response = flask_client.get(
            path + '?generation_id=test-gid',
            follow_redirects=False,
        )
        assert response.status_code == 301
        assert response.headers['Location'] == '/?generation_id=test-gid'


@pytest.mark.api
def test_root_react_assets_are_served(flask_client):
    html = flask_client.get('/').data.decode('utf-8')
    asset = re.search(r"/assets/([^\"']+\.(?:js|css))", html)
    assert asset, 'React entry asset missing from root HTML'
    response = flask_client.get('/assets/' + asset.group(1))
    assert response.status_code == 200
    assert response.content_type.startswith(('text/javascript', 'text/css'))
    assert response.data
