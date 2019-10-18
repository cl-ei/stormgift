import time
import json
from random import randint
from aiohttp import web
from config import CDN_URL
from utils.dao import redis_cache, SuperDxjUserSettings, SuperDxjUserAccounts
from website.handlers.lt import render_to_response


def login_required(r_type="html"):
    def deco(f):
        async def wrapped(request):
            try:
                room_id = request.cookies["room_id"]
                dxj_token = request.cookies["dxj_token"]

                key = f"LT_DXJ_TOKEN_{room_id}"
                token_cache = await redis_cache.get(key)
                if token_cache != dxj_token:
                    raise ValueError("Bad mad_token.")

            except (KeyError, ValueError, TypeError):
                if r_type == "html":
                    return web.HTTPFound("/lt/dxj/login")
                else:
                    return web.json_response({"code": 30200, "err_msg": "请登陆后再操作。"})

            return await f(request)
        return wrapped
    return deco


async def login(request):
    context = {"CDN_URL": CDN_URL}
    if request.method.lower() == "post":
        post_data = await request.post()

        room_id = post_data["room_id"]
        password = post_data["password"]

        if password != await SuperDxjUserAccounts.get(user_id=room_id):
            return web.json_response({"code": 40300, "err_msg": "账号或密码错误！"})

        key = f"LT_DXJ_TOKEN_{room_id}"
        dxj_token = f"DXJ_{int(time.time() * 1000):0x}{randint(0x1000, 0xffff):0x}"
        await redis_cache.set(key=key, value=dxj_token, timeout=3600*24*30)

        response = web.json_response({"code": 0})
        response.set_cookie(name="room_id", value=room_id, httponly=True)
        response.set_cookie(name="dxj_token", value=dxj_token, httponly=True)
        return response

    return render_to_response("website/templates/dxj_login.html", context=context)


async def logout(request):
    room_id = request.cookies["room_id"]
    key = f"LT_DXJ_TOKEN_{room_id}"

    await redis_cache.delete(key)
    response = web.HTTPFound("/lt/dxj/login")
    response.del_cookie(name="room_id")
    response.del_cookie(name="dxj_token")

    return response


@login_required()
async def settings(request):
    room_id = request.cookies["room_id"]
    existed_settings = await SuperDxjUserSettings.get(room_id=room_id)
    context = {
        "CDN_URL": CDN_URL,
        "existed_settings": json.dumps(existed_settings),
        "room_id": room_id,
    }
    return render_to_response("website/templates/dxj_settings.html", context=context)


@login_required()
async def change_password(request):
    room_id = request.cookies["room_id"]
    data = await request.post()
    password = data["dxj-password"]
    await SuperDxjUserAccounts.set(user_id=room_id, password=password)

    key = f"LT_DXJ_TOKEN_{room_id}"
    await redis_cache.delete(key=key)
    return web.Response(
        body="密码修改成功！<a href=\"/lt/dxj/login\">重新登录</a>",
        content_type="text/html",
        charset="utf-8",
    )


@login_required(r_type="json")
async def post_settings(request):
    room_id = request.cookies["room_id"]
    data = await request.post()
    try:
        data = json.loads(data["settings"])
    except json.JSONDecodeError:
        return web.json_response({"code": 403, "err_msg": "错误的参数！"})

    config = {}
    account = data["account"].strip()
    if not account:
        return web.json_response({"code": 403, "err_msg": "B站账号错误！"})
    config["account"] = account

    password = data["password"].strip()
    if not password:
        return web.json_response({"code": 403, "err_msg": "B站账号密码错误！"})
    config["password"] = password

    config["carousel_msg"] = [
        msg for msg in data["carousel_msg"]
        if isinstance(msg, str) and 0 < len(msg) <= 30
    ]
    config["carousel_msg_interval"] = int(data["carousel_msg_interval"])
    if config["carousel_msg_interval"] < 30 or config["carousel_msg_interval"] > 240:
        return web.json_response({"code": 403, "err_msg": "轮播弹幕间隔错误！30 ~ 240秒."})

    for k in ("thank_silver", "thank_gold", "thank_follower"):
        config[k] = int(data[k])

    for k in ("thank_silver_text", "thank_gold_text", "thank_follower_text"):
        v = data[k].strip()
        if v:
            config[k] = v

    config["auto_response"] = []
    for pair in data["auto_response"]:
        if not isinstance(pair, list):
            continue
        if len(pair) != 2:
            continue

        k = pair[0].strip()
        if not isinstance(k, str) or len(k) > 30:
            continue

        v = pair[1].strip()
        if not isinstance(v, str) or len(v) > 30:
            continue
        config["auto_response"].append([k, v])

    await SuperDxjUserSettings.set(room_id=room_id, **config)
    return web.json_response({"code": 0, "err_msg": "设置成功！"})

