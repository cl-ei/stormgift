import datetime
from jinja2 import Template
from aiohttp import web
from utils.biliapi import BiliApi
from utils.dao import CookieOperator, AcceptorBlockedUser
from utils.db_raw_query import AsyncMySQL
from config import CDN_URL


async def handler(request):
    data = await request.post()
    print(data)
    return


app = web.Application()
app.add_routes([
    web.get('/', handler),
    web.post('/', handler),
])
web.run_app(app, port=60000)
