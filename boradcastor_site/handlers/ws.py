import sys
from aiohttp import web
from utils.mq import mq_raffle_broadcast


async def log_broadcast_handler(request):
    remote_ip = request.headers.get("X-Real-IP", "")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    request.app['websockets'].add(ws)
    await ws.send_str(f"Connected. Your ip is {remote_ip}, transferring data...\n")
    try:
        async for msg in ws:
            pass
    finally:
        request.app['websockets'].discard(ws)
    return ws


async def notify_log_broadcast(app, q):
    while True:
        content = await q.get()
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            continue

        for ws in set(app['websockets']):
            await ws.send_str(content)


async def raffle_broadcast_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    request.app['websockets_raffle'].add(ws)
    try:
        async for msg in ws:
            pass
    finally:
        request.app['websockets_raffle'].discard(ws)
    return ws


async def notify_raffle(app):
    if sys.platform != "linux":
        return

    while True:
        message = await mq_raffle_broadcast.get()
        for ws in set(app['websockets_raffle']):
            await ws.send_str(f"{message}\n")
