#!/usr/bin/env python3
"""Child process for the TRUE subprocess restart test.

Phase B of the restart scenario runs here: a completely separate Python
process (fresh interpreter, fresh module state, no inherited objects)
serves GET/PUT for a generation that was created by a different process.
Module/app state is resolved from the RPM_GENERATOR_DB database only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/src')

import app as app_module  # noqa: E402


def main() -> None:
    command = sys.argv[1]  # 'get' | 'put'
    payload = json.load(sys.stdin)
    generation_id = payload['generation_id']
    client = app_module.app.test_client()

    if command == 'get':
        resp = client.get(f'/api/module/{generation_id}')
        body = json.loads(resp.data)
        result = {
            'http': resp.status_code,
            'status': body.get('status'),
            'topic': (body.get('module') or {}).get('topic'),
            'context_phase': (body.get('context') or {}).get('phase'),
            'context_cp_source': ((body.get('context') or {}).get('cp') or {}).get('source_document_id'),
            'error_code': ((body.get('errors') or [{}])[0].get('code')),
        }
    else:  # put
        resp = client.put(f'/api/module/{generation_id}', json={'module': payload['module']})
        body = json.loads(resp.data)
        result = {
            'http': resp.status_code,
            'status': body.get('status'),
            'error_code': ((body.get('errors') or [{}])[0].get('code')),
        }

    json.dump(result, sys.stdout)


if __name__ == '__main__':
    main()
