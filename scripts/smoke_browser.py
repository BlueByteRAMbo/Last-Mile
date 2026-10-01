"""Windows browser smoke test using installed Chrome and the backend's websockets.

Run: backend/.venv/Scripts/python scripts/smoke_browser.py
Uses isolated SQLite, ports 8012/5178/9225, fast test riders and a temporary browser
profile. No production orders are created. Screenshots go to the temp directory.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

ROOT = Path(__file__).resolve().parents[1]


def serve():
    sys.path.insert(0, str(ROOT / 'backend'))
    from contextlib import asynccontextmanager
    import uvicorn
    from app import main, simulator
    from app.world import world
    original = main.app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            simulator.state['order_spawn_rate'] = 0
            for store in world.stores:
                store.packing_seconds_per_order = 2
            for rider in world.riders:
                rider.speed_kmh = 100
            yield
    main.app.router.lifespan_context = lifespan
    uvicorn.run(main.app, host='127.0.0.1', port=8012, log_level='error')


def fetch(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


async def check():
    live = '--live' in sys.argv
    frontend = 'http://127.0.0.1:5176' if live else 'http://127.0.0.1:5178'
    backend = 'http://127.0.0.1:8000' if live else 'http://127.0.0.1:8012'
    env = dict(os.environ, DATABASE_URL='sqlite+aiosqlite:///:memory:', VITE_API_URL='http://127.0.0.1:8012')
    artifact = Path(tempfile.mkdtemp(prefix='routex-phase5-'))
    log = (artifact / 'servers.log').open('w', encoding='utf-8')
    processes = []
    errors = []
    try:
        if not live:
            processes.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve'], cwd=ROOT / 'backend', env=env, stdout=log, stderr=log))
            processes.append(subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5178', '--strictPort'], cwd=ROOT, env=env, stdout=log, stderr=log))
        chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        processes.append(subprocess.Popen([str(chrome), '--headless=new', '--no-first-run', '--no-default-browser-check',
            '--remote-debugging-port=9225', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
            f'--user-data-dir={artifact / "profile"}', 'about:blank'], stdout=log, stderr=log))
        for _ in range(60):
            try:
                pages = fetch('http://127.0.0.1:9225/json')
                fetch(backend + '/catalog')
                with urllib.request.urlopen(frontend, timeout=2):
                    pass
                break
            except Exception:
                await asyncio.sleep(.25)
        page = next(p for p in pages if p['type'] == 'page')
        async with websockets.connect(page['webSocketDebuggerUrl'], max_size=20_000_000) as ws:
            seq = 0
            async def command(method, params=None):
                nonlocal seq
                seq += 1
                await ws.send(json.dumps({'id': seq, 'method': method, 'params': params or {}}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get('method') == 'Runtime.exceptionThrown':
                        detail = message['params']['exceptionDetails']
                        errors.append(detail.get('exception', {}).get('description', detail.get('text')))
                    if message.get('id') == seq:
                        if 'error' in message:
                            raise AssertionError(message['error'])
                        return message.get('result', {})
            async def js(expression):
                result = await command('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
                if 'exceptionDetails' in result:
                    raise AssertionError(result['exceptionDetails'].get('text'))
                return result.get('result', {}).get('value')
            async def until(expression, timeout=35):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if await js(f'Boolean({expression})'):
                        return
                    await asyncio.sleep(.3)
                await screenshot('failure.png')
                (artifact / 'failure.json').write_text(json.dumps({
                    'condition': expression, 'url': await js('location.href'),
                    'page_text': await js('document.body.innerText'),
                    'orders': fetch(backend + '/orders'),
                    'riders': fetch(backend + '/riders'),
                    'traffic_zones': fetch(backend + '/traffic_zones'),
                    'errors': errors,
                }, indent=2), encoding='utf-8')
                raise AssertionError(f'Timed out: {expression}; diagnostics: {artifact}')
            async def screenshot(name):
                data = await command('Page.captureScreenshot', {'format': 'png'})
                (artifact / name).write_bytes(base64.b64decode(data['data']))
            await command('Runtime.enable')
            await command('Page.enable')
            await command('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
            if live:
                await command('Page.navigate', {'url': frontend + '/#ops'})
                await until("document.querySelectorAll('.ops-store-marker').length === 5")
                await screenshot('live-ops.png')
                order = next(o for o in fetch(backend + '/orders') if o['rider_id'] and o['status'] in ('assigned', 'packing', 'packed', 'out_for_delivery'))
                await command('Page.navigate', {'url': frontend + '/#journey/' + order['id']})
                await until("document.querySelector('.journey-hud') && document.querySelectorAll('.stock-row').length === 5")
                await until("Array.from(document.querySelectorAll('.journey-label')).some(el => el.textContent.includes('Rider'))")
                await asyncio.sleep(3)
                assert 'Reconnecting' not in await js('document.body.innerText')
                await screenshot('live-journey.png')
                await command('Page.navigate', {'url': frontend + '/#track/' + order['id']})
                await until("document.querySelector('.customer-details') && document.body.innerText.includes('Live updates')")
                await screenshot('live-tracker.png')
                await command('Page.addScriptToEvaluateOnNewDocument', {'source': 'window.socketCount=0; const NativeSocket=window.WebSocket; window.WebSocket=class extends NativeSocket { constructor(...args) { super(...args); window.socketCount++; } };'})
                await command('Page.navigate', {'url': frontend + '/#track/nonexistent-regression-order'})
                await until("document.body.innerText.includes('no longer available')")
                count = await js('window.socketCount')
                await asyncio.sleep(4)
                assert await js('window.socketCount') == count
                assert not errors, errors
                print(json.dumps({'live_browser': 'passed', 'warehouses': 5, 'rider_assigned': order['rider_id'], 'tracking': 'stable', 'missing_order_retry_loop': False, 'screenshots': str(artifact)}))
                return
            await command('Page.navigate', {'url': 'http://127.0.0.1:5178/#shop'})
            await until("document.querySelectorAll('.product-card').length === 22")
            await screenshot('shop.png')
            await js("document.querySelector('[aria-label=\"Add Curd 400g\"]').click(); const input = document.querySelector('input[placeholder=\"Customer name\"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Browser Customer'); input.dispatchEvent(new Event('input', {bubbles:true}));")
            # Curd is stocked in Powai but not Andheri; use a nearby stocked address
            # for the fast browser scenario. Stock exclusion is covered in pytest.
            await js("const address=document.querySelector('select'); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(address, 'DS-3'); address.dispatchEvent(new Event('change', {bubbles:true}));")
            await js("document.querySelector('form').requestSubmit()")
            await until("location.hash.startsWith('#journey/') && document.querySelector('.journey-hud')")
            oid = await js("decodeURIComponent(location.hash.split('/')[1])")
            await until("document.querySelector('.journey-hud').innerText.includes('Packing') || document.querySelector('.journey-hud').innerText.includes('Packed') || document.querySelector('.journey-hud').innerText.includes('Out For Delivery') || document.querySelector('.journey-hud').innerText.includes('Delivered')")
            print('Checkout and live journey passed.', flush=True)
            await screenshot('journey.png')
            # Wait for a real active leg, then aim at its live rider marker rather
            # than the city-wide map center (which may affect no route).
            await until("document.querySelector('.journey-hud').innerText.includes('Out For Delivery')", timeout=60)
            await asyncio.sleep(2.1)
            await js("Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Simulate traffic')).click()")
            if await js("!!document.querySelector('.mapboxgl-canvas') && !document.querySelector('.map-unavailable')"):
                await asyncio.sleep(.3)
                rect = await js("(() => { const el=Array.from(document.querySelectorAll('.journey-marker')).find(el => el.textContent.includes('Browser Customer') && el.textContent.includes('Rider')); const r=el.querySelector('.journey-dot').getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()")
                await command('Input.dispatchMouseEvent', {'type': 'mousePressed', 'button': 'left', 'clickCount': 1, **rect})
                await command('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'button': 'left', 'clickCount': 1, **rect})
                await until("document.querySelector('[role=status]')?.textContent.includes('Keeping current route') || document.querySelector('[role=status]')?.textContent.includes('Faster route selected')")
                zones = fetch('http://127.0.0.1:8012/traffic_zones')
                assert zones
                journey = fetch(f'http://127.0.0.1:8012/orders/{oid}/journey')
                assert journey['route_history']
                print('Traffic placement and live route decision passed.', flush=True)
            await command('Page.navigate', {'url': f'http://127.0.0.1:5178/#track/{oid}'})
            await until("document.querySelector('.customer-details') && document.body.innerText.includes('Live updates')")
            await until("document.querySelector('h1')?.textContent === 'At your doorstep.'", timeout=100)
            assert not await js("document.body.innerText.includes('cost difference')")
            await asyncio.sleep(2)
            await screenshot('tracker.png')
            await command('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
            await asyncio.sleep(1)
            await screenshot('tracker-mobile.png')
            assert not errors, errors
            print(json.dumps({'browser': 'passed', 'order': oid, 'screenshots': str(artifact),
                'map_loaded': not await js("!!document.querySelector('.map-unavailable')"), 'runtime_errors': len(errors)}))
    finally:
        for process in reversed(processes):
            process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()


if __name__ == '__main__':
    if '--serve' in sys.argv:
        serve()
    else:
        asyncio.run(check())
