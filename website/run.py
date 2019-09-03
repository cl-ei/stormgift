from aiohttp import web
from website.handlers import lt, cq


app = web.Application()
app.add_routes([
    web.get('/lt', lt.lt),
    web.post('/lt/api', lt.api),
    web.get('/lt/query_gifts', lt.query_gifts),
    web.get('/lt/query_raffles', lt.query_raffles),
    web.get('/lt/query_raffles_by_user', lt.query_raffles_by_user),
    web.route('*', "/lt/cq_handler", cq.handler),
])
web.run_app(app, port=1024)
