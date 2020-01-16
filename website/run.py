import asyncio
import datetime
from aiohttp import web
from website.handlers import lt, cq, dxj


async def main():
    from config.log4 import web_access_logger

    @web.middleware
    async def log_access(request, handler):
        ua = request.headers.get("User-Agent", "NON_UA")
        web_access_logger.info(f"{request.method} {request.url} <*> {request.remote} {ua}")
        return await handler(request)

    @web.middleware
    async def set_server_name(request, handler):
        try:
            resp = await handler(request)
        except Exception as e:
            resp = web.Response(status=500, text=f"{e}")

        resp.headers['Server'] = 'madliar/2.1.1a11(Darwin)'
        return resp

    app = web.Application(middlewares=[log_access, set_server_name])

    async def home_page(request):
        return web.Response(text=f"OK.\n\n{datetime.datetime.now()}")

    app.add_routes([
        web.get('/', home_page),
        web.get('/lt_{token}', lt.lt),

        web.route('*', '/lt/dxj/login', dxj.login),

        web.get('/lt/dxj/settings', dxj.settings),
        web.post('/lt/dxj/change_password', dxj.change_password),
        web.post('/lt/dxj/post_settings', dxj.post_settings),
        web.get('/lt/dxj/logout', dxj.logout),

        web.post('/lt/login', lt.login),
        web.get('/lt/settings', lt.settings),
        web.post('/lt/post_settings', lt.post_settings),
        web.get('/lt/broadcast', lt.broadcast),
        web.get('/lt/query_gifts', lt.query_gifts),
        web.get('/lt/query_raffles', lt.query_raffles),
        web.get('/lt/query_raffles_by_user', lt.query_raffles_by_user),
        web.get('/lt/trends_qq_notice', lt.trends_qq_notice),
        web.route('*', "/lt/cq_handler", cq.handler),
    ])
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 1024)
    await site.start()
    print("Site started.")

    while True:
        await asyncio.sleep(100)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
