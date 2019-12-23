import asyncio
from aiohttp import web
from acceptor_site.handlers import lt, cq, dxj


async def main():
    app = web.Application()
    app.add_routes([
        web.get('/lt_{token}', lt.lt),
        web.get('/lt/dxj/login', dxj.login),
        web.post('/lt/dxj/login', dxj.login),
        web.get('/lt/dxj/settings', dxj.settings),
        web.post('/lt/dxj/change_password', dxj.change_password),
        web.post('/lt/dxj/post_settings', dxj.post_settings),
        web.get('/lt/dxj/logout', dxj.logout),

        web.get('/lt/broadcast', lt.raffle_broadcast),
        web.post('/lt/login', lt.login),
        web.get('/lt/settings', lt.settings),
        web.post('/lt/post_settings', lt.post_settings),
        web.get('/lt/query_gifts', lt.query_gifts),
        web.get('/lt/query_raffles', lt.query_raffles),
        web.get('/lt/query_raffles_by_user', lt.query_raffles_by_user),
        web.get('/lt/trends_qq_notice', lt.trends_qq_notice),
        web.route('*', "/lt/cq_handler", cq.handler),
        web.post('/lt/calc_sign', lt.calc_sign),
    ])
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 80)
    await site.start()
    print("Site started.")

    while True:
        await asyncio.sleep(100)


asyncio.run(main())
