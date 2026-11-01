"""Marketplace copy and buyer demo use only active, checked evidence."""
import pytest

from app.marketplace import build_post
from test_app import client  # noqa: F401


def sample(client):
    main, c = client
    path = c.post('/sample', follow_redirects=False).headers['location']
    listing, key = path.split('?k=')
    c.post(f'{listing}/sample-detail?k={key}')  # the close-up Spark asks for
    c.post(f'{listing}/check?k={key}')
    report = c.post(f'{listing}/report?k={key}', follow_redirects=False).headers['location']
    return path, report.rsplit('/', 1)[-1]


def test_post_removes_contradiction_from_description_and_title():
    payload = {'claims': [{'text': 'No scratches', 'verdict': {
        'status': 'contradicted', 'detail': 'peeling on the tabletop near the edge'}}],
        'photos': {'detail': 'd', 'front': 'f', 'side': 's'}}
    post = build_post({'title': 'No scratches', 'description': 'NO scratches. Pick up only.'},
                      payload, 'https://example.test/r/token')
    assert 'no scratches' not in str(post).lower()
    assert 'Pick up only.' in post['description']
    assert 'Photos show: peeling on the tabletop near the edge' in post['description']
    assert 'Evidence report: https://example.test/r/token' in post['description']
    assert [p.rsplit('/', 1)[-1] for p in post['photos']] == ['front', 'side', 'detail']
    post = build_post({'title': 'Table', 'description': 'Totally scratch free'}, payload, 'https://example.test/r/t')
    assert 'Totally scratch free' not in post['description']
    assert post['description_omitted']


def test_active_api_demo_and_share(client):
    main, c = client
    path, token = sample(client)
    api = c.get(f'/api/r/{token}').json()
    post = api['post']
    assert set(post) == {'title', 'description', 'description_omitted', 'photos', 'report_url'}
    assert 'No scratches or stains' not in post['description']
    assert 'Photos show:' in post['description']
    assert 'Seller says: Solid oak, not veneer' in post['description']
    assert all(c.get(url).status_code == 200 for url in post['photos'])
    demo = c.get(f'/r/{token}/listing')
    assert demo.status_code == 200
    assert 'DEMO · Not Facebook Marketplace · Not affiliated with Meta' in demo.text
    assert 'Verified evidence · See report' in demo.text
    assert '2 ✓</b> · <b class="no">1 ✕</b> · <b class="na">1 ?' in demo.text
    assert 'Sample · Not a real listing' in demo.text
    assert f'content="http://testserver/r/{token}/card.jpg"' in demo.text
    assert '<script' not in demo.text and '<button disabled>Message</button>' in demo.text
    share = c.get(path).text
    for label in ('Post it on Marketplace', 'Copy post', 'Open Marketplace', 'Preview as a buyer'):
        assert label in share
    assert f'/r/{token}/listing' in c.get(f'/r/{token}').text


@pytest.mark.parametrize('state', ['revoked', 'invalidated', 'expired'])
def test_inactive_report_has_no_post_or_demo_verdicts(client, state):
    main, c = client
    path, token = sample(client)
    if state == 'expired':
        main.store.db.execute("UPDATE reports SET expires_at='2000-01-01T00:00:00+00:00' WHERE token=?", (token,))
    else:
        main.store.db.execute('UPDATE reports SET state=? WHERE token=?', (state, token))
    assert 'post' not in c.get(f'/api/r/{token}').json()
    response = c.get(f'/r/{token}/listing')
    assert response.status_code == 200
    assert 'Report withdrawn' in response.text if state == 'revoked' else 'Report no longer valid' in response.text
    for hidden in ('✓', '✕', 'Photo-checked', 'Photos show:', '/photo/', 'Verified evidence'):
        assert hidden not in response.text
    assert 'Copy post' not in c.get(path).text


def test_unknown_listing_demo(client):
    assert client[1].get('/r/missing/listing').status_code == 404


def test_post_preserves_description_without_contradictions():
    post = build_post({'title': 'Dining table', 'description': 'Pick up only. Barely used.'},
                      {'claims': [], 'photos': {}}, 'https://example.test/r/t')
    assert post['title'] == 'Dining table'
    assert post['description'].startswith('Pick up only. Barely used.\n\n')
