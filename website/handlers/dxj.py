import time
from random import randint
from aiohttp import web
from config import CDN_URL
from utils.dao import redis_cache
from website.handlers.lt import render_to_response


def login_required(f):
    async def wrapped(request):
        try:
            room_id = request.cookies["room_id"]
            dxj_token = request.cookies["dxj_token"]

            key = f"LT_DXJ_TOKEN_{room_id}"
            token_cache = await redis_cache.get(key)
            if token_cache != dxj_token:
                raise ValueError("Bad mad_token.")

        except (KeyError, ValueError, TypeError):
            return web.HTTPFound("/lt/dxj/login")

        return await f(request)
    return wrapped


async def login(request):
    context = {"CDN_URL": CDN_URL}
    if request.method.lower() == "post":
        post_data = await request.post()

        room_id = post_data["room_id"]
        password = post_data["password"]

        print(f"room_id: {room_id}, password: {password}")

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


@login_required
async def settings(request):
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/dxj_settings.html", context=context)


async def post_settings(request):
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/website_homepage.html", context=context)
