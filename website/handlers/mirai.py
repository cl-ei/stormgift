import time
import aiohttp
import datetime
from aiohttp import web
from utils.dao import redis_cache
from config.log4 import cqbot_logger as logging


async def handler(request):
    print(f"request: {type(request)}")
    return web.Response(text="", status=204)
