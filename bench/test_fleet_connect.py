"""User-authorized live test: gateway /ws connect + agents.list (with Origin header)."""
import asyncio
import json
import websockets
from jarvis.config import settings
from jarvis.brain.fleet import _ws_url, _req, _connect_params, _origin

async def main():
    url = _ws_url()
    print("connecting:", url.split("?")[0], "origin:", _origin())
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {settings.openclaw_token}"}, origin=_origin(), open_timeout=10, max_size=16*1024*1024) as ws:
        ch = json.loads(await ws.recv())
        connect = _req("connect", _connect_params())
        await ws.send(json.dumps(connect))
        for _ in range(8):
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
            except asyncio.TimeoutError:
                print("  (timeout)"); break
            if m.get("id") == connect["id"]:
                print("CONNECT RESP:", json.dumps(m)[:500]); break
            print(f"  ev type={m.get('type')} event={m.get('event')}: {json.dumps(m)[:140]}")
        al = _req("agents.list", {})
        await ws.send(json.dumps(al))
        for _ in range(8):
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
            except (asyncio.TimeoutError, Exception) as e:
                print("  end:", type(e).__name__); break
            if m.get("id") == al["id"]:
                print("AGENTS.LIST:", json.dumps(m)[:900]); break
            print(f"  ev {m.get('type')}/{m.get('event')}: {json.dumps(m)[:120]}")

asyncio.run(main())
