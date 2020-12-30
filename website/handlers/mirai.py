import time
import aiohttp
from aiohttp.web_request import Request
import datetime
from aiohttp import web
from utils.dao import redis_cache
from config.log4 import cqbot_logger as logging


async def handler(request: Request):
    data = await request.json()
    print(f"request: {request.method}\ndata: {data}")
    return web.Response(text="", status=204)
