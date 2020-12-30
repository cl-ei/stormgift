import time
import aiohttp
from aiohttp.web_request import Request
import datetime
from aiohttp import web
from utils.dao import redis_cache
from config.log4 import cqbot_logger as logging


async def handler(request: Request):
    print(f"request: {request.method}")
    return web.Response(text="", status=204)
