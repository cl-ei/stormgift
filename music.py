import os
import asyncio
import aiohttp
import weakref
import datetime
from aiohttp import web
from jinja2 import Template

with open("music.html", encoding="utf-8") as f:
    music_html = f.read()


async def main():
    app = web.Application()
    app['ws'] = weakref.WeakSet()

    async def home_page(request):
        music_files = os.listdir("./live_room_statics/music/")
        image_files = os.listdir("./live_room_statics/img/")

        context = {
            "title": "grafana",
            "background_images": ["/static/img/" + img for img in image_files],
            "background_musics": ["/static/music/" + mp3 for mp3 in music_files],
        }
        template = Template(music_html)
        return web.Response(text=template.render(context), content_type="text/html")

    async def command(request):
        cmd = request.match_info['cmd']
        print(f"cmd: {cmd}")
        return web.Response(status=206)

    async def ws_server(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        request.app['ws'].add(ws)
        try:
            async for msg in ws:
                pass
        finally:
            request.app['ws'].discard(ws)
        return ws

    async def push_message_to_web_page(message):
        for ws in set(app['ws']):
            await ws.send_str(f"{message}\n")

    app.add_routes([
        web.get('/', home_page),
        web.get('/command/{cmd}', command),
        web.get('/ws', ws_server),
        web.static('/static', "./live_room_statics")
    ])
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 4096)
    await site.start()
    print("Site started.\nhttp://127.0.0.1:4096")

    while True:
        await asyncio.sleep(10)
        await push_message_to_web_page(f"OK.\n\n{datetime.datetime.now()}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())


async def get_song():
    song_name = "美丽新世界"

    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,image/apng,*/*;q=0.8"
        ),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/70.0.3538.110 Safari/537.36"
        ),
    }
    req_params = {
        "method": "post",
        "url": "http://music.163.com/api/search/pc",
        "headers": headers,
        "data": {"s": song_name, "type": 1, "limit": 50, "offset": 0},
    }

    async with aiohttp.request(**req_params) as response:
        status_code = response.status
        content = await response.text()

    url = "http://music.163.com/song/media/outer/url?id=562598065.mp3"

    print(status_code)
    print(content)
