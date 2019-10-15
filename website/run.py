import os
import sys
import asyncio
import weakref
import traceback
from utils.mq import mq_raffle_broadcast
from aiohttp import web
from website.handlers import lt, cq, dxj

if sys.platform == "linux":
    import pyinotify

    monitor_log_file = "/home/wwwroot/log/stormgift.log"
    log_file_content_size = os.path.getsize(monitor_log_file)
    log_file_changed_content_q = asyncio.Queue()

else:
    pyinotify = None
    monitor_log_file = ""
    log_file_content_size = 0
    log_file_changed_content_q = asyncio.Queue()


def handle_read_callback(notifier):
    global log_file_content_size
    current_size = os.path.getsize(monitor_log_file)
    try:
        with open(monitor_log_file, "rb") as f:
            f.seek(log_file_content_size)
            content = f.read(current_size - log_file_content_size)
            log_file_changed_content_q.put_nowait(content)
    except Exception as e:
        return f"Error happened in handle_read_callback: {e}\n{traceback.format_exc()}"
    log_file_content_size = current_size


async def ws_log_broadcast_handler(request):
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


async def ws_notify_log_broadcast(app):
    while True:
        content = await log_file_changed_content_q.get()
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            continue

        for ws in set(app['websockets']):
            await ws.send_str(content)


async def ws_raffle_broadcast_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    request.app['websockets_raffle'].add(ws)
    try:
        async for msg in ws:
            pass
    finally:
        request.app['websockets_raffle'].discard(ws)
    return ws


async def ws_notify_raffle(app):
    if sys.platform != "linux":
        return

    while True:
        message, has_read = await mq_raffle_broadcast.get()
        for ws in set(app['websockets_raffle']):
            await ws.send_str(f"{message}\n")
        await has_read()


async def proc_status(request):
    console_conn_count = len(request.app['websockets'])
    raffle_conn_count = len(request.app['websockets_raffle'])
    response = f"console_conn_count: {console_conn_count},\nraffle_conn_count: {raffle_conn_count}"
    return web.Response(text=response)


async def start_web_site():
    app = web.Application()
    app.add_routes([
        web.get('/lt', lt.lt),
        web.get('/lt/dxj/login', dxj.login),
        web.post('/lt/dxj/login', dxj.login),
        web.get('/lt/dxj/settings', dxj.settings),
        web.post('/lt/dxj/post_settings', dxj.post_settings),
        web.get('/lt/dxj/logout', dxj.logout),
        web.get('/lt/status', proc_status),
        web.get('/console_wss', ws_log_broadcast_handler),
        web.get('/raffle_wss', ws_raffle_broadcast_handler),
        web.get('/lt/broadcast', lt.raffle_broadcast),
        web.post('/lt/login', lt.login),
        web.get('/lt/settings', lt.settings),
        web.post('/lt/post_settings', lt.post_settings),
        web.get('/lt/query_gifts', lt.query_gifts),
        web.get('/lt/query_raffles', lt.query_raffles),
        web.get('/lt/query_raffles_by_user', lt.query_raffles_by_user),
        web.get('/lt/trends_qq_notice', lt.trends_qq_notice),
        web.route('*', "/lt/cq_handler", cq.handler),
    ])
    app['websockets'] = weakref.WeakSet()
    app['websockets_raffle'] = weakref.WeakSet()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 1024)
    await site.start()
    print("Site started.")
    await asyncio.gather(ws_notify_log_broadcast(app), ws_notify_raffle(app))


loop = asyncio.get_event_loop()
if pyinotify:
    wm = pyinotify.WatchManager()
    pyinotify.AsyncioNotifier(
        wm,
        loop,
        default_proc_fun=lambda *a, **k: None,
        callback=handle_read_callback
    )
    wm.add_watch(monitor_log_file, pyinotify.IN_MODIFY)
loop.run_until_complete(start_web_site())
