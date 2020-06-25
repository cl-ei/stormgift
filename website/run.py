import asyncio
import datetime
from aiohttp import web
from website.handlers import lt, cq_zy


async def main():
    from config.log4 import web_access_logger

    @web.middleware
    async def log_access(request, handler):
        ua = request.headers.get("User-Agent", "NON_UA")
        resp = await handler(request)
        web_access_logger.info(f"{request.method}-{resp.status} {request.remote} {request.url}\n\t{ua}")
        return resp

    @web.middleware
    async def set_server_name(request, handler):
        try:
            resp = await handler(request)
        except Exception as e:
            status = getattr(e, "status", 500)
            resp = web.Response(status=status, text=f"{e}")

        resp.headers['Server'] = 'madliar/2.1.1a11(Darwin)'
        return resp

    app = web.Application(middlewares=[log_access, set_server_name])

    async def home_page(request):
        return web.Response(text=f"OK.\n\n{datetime.datetime.now()}")

    app.add_routes([
        web.get('/', home_page),
        web.get('/lt_{token}', lt.lt),
        web.get('/bili/q/{user_id}/{web_token}', lt.q),

        web.post('/lt/login', lt.login),
        web.get('/lt/qr_code_login/{token}', lt.qr_code_login),
        web.get('/lt/qr_code_result', lt.qr_code_result),
        web.get('/lt/settings', lt.settings),
        web.post('/lt/post_settings', lt.post_settings),

        web.get('/lt/broadcast', lambda x: web.HTTPFound('https://www.madliar.com/bili/broadcast')),
        web.get('/lt/query_gifts', lambda x: web.HTTPFound('https://www.madliar.com/bili/guards')),
        web.get('/lt/query_raffles', lambda x: web.HTTPFound('https://www.madliar.com/bili/raffles')),
        web.get('/lt/query_raffles_by_user', lambda x: web.HTTPFound('https://www.madliar.com/bili/raffles')),

        web.get('/lt/trends_qq_notice', lt.trends_qq_notice),
        web.route('*', "/lt/cq_handler", cq_zy.handler),
    ])
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 2020)
    await site.start()
    print("Site started.")

    while True:
        await asyncio.sleep(100)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
