import os
import asyncio
import pyinotify
from aiohttp import web
from website.handlers import lt, cq

monitor_log_file = "./test.py"
log_file_content_size = os.path.getsize(monitor_log_file)
log_file_changed_content_q = asyncio.Queue()


def handle_read_callback(notifier):
    global log_file_content_size
    current_size = os.path.getsize(monitor_log_file)

    with open(monitor_log_file, "rb") as f:
        f.seek(log_file_content_size)
        content = f.read(current_size - log_file_content_size)
        log_file_changed_content_q.put_nowait(content)
    log_file_content_size = current_size


async def start_web_site():
    app = web.Application()
    app.add_routes([
        web.get('/lt', lt.lt),
        web.post('/lt/login', lt.login),
        web.get('/lt/settings', lt.settings),
        web.post('/lt/post_settings', lt.post_settings),
        web.get('/lt/query_gifts', lt.query_gifts),
        web.get('/lt/query_raffles', lt.query_raffles),
        web.get('/lt/query_raffles_by_user', lt.query_raffles_by_user),
        web.get('/lt/trends_qq_notice', lt.trends_qq_notice),
        web.route('*', "/lt/cq_handler", cq.handler),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 1024)
    await site.start()
    print("Site started.")

    while True:
        content = await log_file_changed_content_q.get()
        print(content)


loop = asyncio.get_event_loop()
wm = pyinotify.WatchManager()
pyinotify.AsyncioNotifier(
    wm,
    loop,
    default_proc_fun=lambda *a, **k: None,
    callback=handle_read_callback
)
wm.add_watch(monitor_log_file, pyinotify.IN_MODIFY)
loop.run_until_complete(start_web_site())
