"""Run expensive replay away from both the live world and the event loop."""
import asyncio
import json
import sys

_lock = asyncio.Lock()
_result = None


async def comparison():
    global _result
    async with _lock:
        if _result is None:
            process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.benchmark',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            if process.returncode:
                raise RuntimeError('Comparison replay failed')
            _result = json.loads(stdout)
        return _result
