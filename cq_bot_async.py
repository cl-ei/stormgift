import re
import time
import json
import uuid
import hashlib
import datetime
import requests
import traceback
from random import choice, randint, random
import aiohttp
from aiohttp import web
from utils.cq import qq, qq_zy
from config.log4 import cqbot_logger as logging
from utils.dao import HansyQQGroupUserInfo, RaffleToCQPushList
from utils.biliapi import BiliApi
from utils.highlevel_api import ReqFreLimitApi
from utils.highlevel_api import DBCookieOperator





async def handler(request):
    x_self_id = int(request.headers['X-Self-ID'])
    if x_self_id == 250666570:
        qq_bot = qq_zy
    else:
        qq_bot = qq

    context = await request.json()
    context["qq_bot"] = qq_bot

    if context["post_type"] == "message":
        response = await BotHandler.handle_message(context)

    elif context["post_type"] == "notice":
        response = await BotHandler.handle_notice(context)

    elif context["post_type"] == "request":
        response = await BotHandler.handle_request(context)

    else:
        response = None

    if isinstance(response, dict) and response:
        return web.Response(text=json.dumps(response), content_type="application/json")
    else:
        return web.Response(text="", status=204)


app = web.Application()
app.add_routes([
    web.get('/', handler),
    web.post('/', handler),
])
web.run_app(app, port=60000)
