import json


def test_stats_summary_omits_subject_breakdown(flask_client):
    response = flask_client.get('/api/stats?summary=1')
    assert response.status_code == 200
    data = json.loads(response.data)
    stats = data['statistics']
    assert 'total_fragments' in stats
    assert 'total_cp_entries' in stats
    assert 'total_documents' in stats
    assert 'cp_by_subject' not in stats
