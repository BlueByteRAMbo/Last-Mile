"""Check the real comparison subprocess without changing a running server's data."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import httpx
import websockets


async def check():
    root = Path(__file__).resolve().parents[1]
    log = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-c',
        "from app import routing; routing.MAPBOX_TOKEN=None; import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8013, log_level='error')"],
        cwd=root / 'backend', env=dict(os.environ, DATABASE_URL='sqlite+aiosqlite:///:memory:'),
        stdout=log, stderr=log)
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8013', timeout=100) as client:
            for _ in range(40):
                try:
                    await client.get('/catalog')
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(.2)
            created = (await client.post('/orders', json={'customer_lat': 19.1, 'customer_lng': 72.85,
                       'items': [{'sku': 'SKU-CURD', 'name': 'Curd', 'qty': 1}]})).json()
            async with websockets.connect('ws://127.0.0.1:8013/ws') as ws:
                task = asyncio.create_task(client.get('/analytics/comparison'))
                ticks = 0
                while not task.done():
                    message = json.loads(await asyncio.wait_for(ws.recv(), 6))
                    assert message['type'] == 'tick'
                    ticks += 1
                response = await task
                if response.status_code != 200:
                    log.seek(0)
                    raise AssertionError(log.read()[-6000:])
                result = response.json()
                assert set(result['results']) == {'nearest', 'optimized'}
                assert result['order_count'] == 36
                assert any(o['id'] == created['id'] for o in (await client.get('/orders')).json())
                assert (await client.get('/analytics/comparison')).json() == result
                print(json.dumps({'comparison': 'passed', 'live_ticks_during_replay': ticks, **result}))
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    asyncio.run(check())
