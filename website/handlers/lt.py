import os
import time
import json
import aiohttp
import asyncio
import traceback
from aiohttp import web
from random import randint
from jinja2 import Template
from utils.cq import async_zy
from config import CDN_URL, g
from utils.biliapi import BiliApi
from config.log4 import lt_login_logger
from utils.highlevel_api import DBCookieOperator
from config.log4 import website_logger as logging
from utils.dao import redis_cache, LTUserSettings
from utils.dao import LtUserLoginPeriodOfValidity
from utils.images import DynamicPicturesProcessor


BROWSER_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,image/apng,*/*;q=0.8"
    ),
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/70.0.3538.110 Safari/537.36"
    ),
}


def request_frequency_control(time_interval=4):
    user_requests_records = []  # [(uniq, time), ... ]

    def deco(f):
        async def wrapped(request):
            host = request.headers.get("Host", "governors")
            ua = request.headers.get("User-Agent", "NON_UA")
            remote = request.remote
            unique_identification = hash((host, ua, remote))

            last_req_time = 0
            for _ in user_requests_records:
                if _[0] == unique_identification:
                    last_req_time = _[1]
                    break

            if time.time() - last_req_time < time_interval:
                return web.Response(text=f"你的请求过于频繁。请{time_interval}秒钟后再试。", content_type="text/html")

            result = await f(request)

            user_requests_records.insert(0, (unique_identification, time.time()))

            while len(user_requests_records) > 2000:
                user_requests_records.pop()

            return result
        return wrapped
    return deco


def render_to_response(template, context=None):
    try:
        with open(template, encoding="utf-8") as f:
            template_context = f.read()
    except IOError:
        template_context = "<center><h3>Template Does Not Existed!</h3></center>"

    template = Template(template_context)
    return web.Response(text=template.render(context or {}), content_type="text/html")


def json_response(data):
    return web.Response(text=json.dumps(data), content_type="application/json")


async def check_login(request):
    try:
        bili_uid = request.cookies["DedeUserID"]
        mad_token = request.cookies["mad_token"]
        bili_uid = int(bili_uid)

        key = f"LT_USER_MAD_TOKEN_{bili_uid}"
        mad_token_cache = await redis_cache.get(key)
        if mad_token != mad_token_cache:
            raise ValueError("Bad mad_token.")

    except (KeyError, ValueError, TypeError):
        return

    return bili_uid


async def lt(request):
    token = request.match_info['token']
    if not token:
        return web.HTTPForbidden()

    ua = request.headers.get("User-Agent", "NON_UA")
    remote_ip = request.remote  # request.headers.get("X-Real-IP", "")
    logging.info(f"LT_ACCESS_TOKEN_RECEIVED: {token}, ip: {remote_ip}. UA: {ua}")

    key = F"LT_ACCESS_TOKEN_{token}"
    r = await redis_cache.get(key=key)
    if not r:
        return web.HTTPNotFound()

    r = await redis_cache.incr(key)
    if r < 4:
        return web.Response(text="<h3>请刷新此页面，直到能够正常显示。</h3>", content_type="text/html")

    await redis_cache.delete(key)
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/website_homepage.html", context=context)


async def q(request):
    user_id = request.match_info['user_id']
    token = request.match_info['web_token']
    key = f"LT_WEB_{user_id}"
    if await redis_cache.get(key=key) != token:
        return web.Response(text=f"你访问了错误的链接！")

    msg = request.query.get("msg")
    from website.handlers.cq_zy import BotHandler
    try:
        r = await BotHandler.handle_private_message(msg=msg, user_id=user_id)
    except Exception as e:
        r = f"处理「{msg}」时发生错误：{e}"
    return web.Response(text=r)


async def login(request):
    data = await request.post()
    account = data['account']
    password = data['password']
    email = data["email"]
    if not account or not password:
        return json_response({"code": 403, "err_msg": "输入错误！检查你的输入!"})

    try:
        flag, obj = await DBCookieOperator.add_user_by_account(
            account=account, password=password, notice_email=email)
    except Exception as e:
        lt_login_logger.error(f"登录失败: {account}-{password}：{e}\n{traceback.format_exc()}")
        return json_response({"code": 500, "err_msg": f"服务器内部发生错误! {e}\n{traceback.format_exc()}"})

    if not flag:
        lt_login_logger.error(f"登录失败: {account}-{password}：{obj}")
        return json_response({"code": 403, "err_msg": f"操作失败！原因：{obj}"})

    await LtUserLoginPeriodOfValidity.update(obj.DedeUserID)

    key = f"LT_USER_MAD_TOKEN_{obj.DedeUserID}"
    mad_token = f"{int(time.time() * 1000):0x}{randint(0x1000, 0xffff):0x}"
    await redis_cache.set(key=key, value=mad_token, timeout=3600*24*30)

    response = json_response({"code": 0, "location": "/lt/settings"})
    response.set_cookie(name="mad_token", value=mad_token, httponly=True)
    response.set_cookie(name="DedeUserID", value=obj.DedeUserID, httponly=True)
    lt_login_logger.info(f"登录成功: {account}-{password}：lt")
    return response


async def qr_code_login(request):
    token = request.match_info['token']
    if not token:
        return web.HTTPForbidden()

    ua = request.headers.get("User-Agent", "NON_UA")
    remote_ip = request.remote  # request.headers.get("X-Real-IP", "")
    logging.info(f"LT_ACCESS_TOKEN_RECEIVED: {token}, ip: {remote_ip}. UA: {ua}")

    key = F"LT_ACCESS_TOKEN_{token}"
    r = await redis_cache.get(key=key)
    if not r:
        return web.HTTPNotFound()
    r = await redis_cache.incr(key)
    if r < 4:
        return web.Response(text="<h3>请刷新此页面，直到能够正常显示。</h3>", content_type="text/html")
    await redis_cache.delete(key)

    url = "https://passport.bilibili.com/qrcode/getLoginUrl"
    async with aiohttp.request("get", url=url, headers=BROWSER_HEADERS) as r:
        bili_response = await r.json()

    context = {
        "CDN_URL": CDN_URL,
        "ts": bili_response["ts"],
        "url": bili_response["data"]["url"],
        "oauthKey": bili_response["data"]["oauthKey"],
    }
    return render_to_response("website/templates/qr_code_login.html", context=context)


async def qr_code_result(request):
    url = "https://passport.bilibili.com/qrcode/getLoginInfo"
    data = {
        'oauthKey': request.query.get("oauthKey"),
        'gourl': 'https://passport.bilibili.com/account/security'
    }

    key = f"LT_OAUTH_KEY_{data['oauthKey']}"
    r = await redis_cache.incr(key)
    await redis_cache.expire(key, 3600*72)
    if r >= 10:
        return json_response({"code": 400, "msg": f"二维码已经过期，请刷新页面。"})

    async with aiohttp.request("post", url=url, data=data, headers=BROWSER_HEADERS) as r:
        bili_response = await r.json()
        headers = r.headers

    if bili_response.get("data") in (-4, -5):
        return json_response({"code": -4})
    elif bili_response.get("code") != 0:
        message = bili_response.get("message") or bili_response.get("msg")
        return json_response({
            "code": -1,
            "msg": f"二维码已过期，请刷新页面。\n(原始返回：{bili_response['code']}: {message})"
        })

    cookies = headers.getall("Set-Cookie")
    cookies_dict = {}
    for c in cookies:
        k, v = c.split(";", 1)[0].split("=", 1)
        cookies_dict[k] = v

    try:
        flag, obj = await DBCookieOperator.add_cookie_by_qrcode(**cookies_dict)
    except Exception as e:
        return json_response({"code": 500, "msg": f"服务器内部发生错误! {e}\n{traceback.format_exc()}"})

    if not flag:
        return json_response({"code": 400, "msg": obj})

    key = f"LT_USER_MAD_TOKEN_{obj.DedeUserID}"
    mad_token = f"{int(time.time() * 1000):0x}{randint(0x1000, 0xffff):0x}"
    await redis_cache.set(key=key, value=mad_token, timeout=3600 * 24 * 30)

    response = json_response({"code": 0, "location": "/lt/settings"})
    response.set_cookie(name="mad_token", value=mad_token, httponly=True)
    response.set_cookie(name="DedeUserID", value=obj.DedeUserID, httponly=True)
    lt_login_logger.info(f"登录成功: DedeUserID: {obj.DedeUserID}-{obj.name}：qrcode")
    return response


async def settings(request):
    context = {"CDN_URL": CDN_URL}
    bili_uid = await check_login(request)
    if not bili_uid:
        context["err_msg"] = "你无权访问此页面。请返回宝藏站点首页，正确填写你的信息，然后点击「我要挂辣条」按钮。"
        return render_to_response("website/templates/settings.html", context=context)

    obj = await DBCookieOperator.get_by_uid(user_id=bili_uid)
    context["user_name"] = obj.name
    context["user_id"] = obj.uid
    context["settings"] = await LTUserSettings.get(uid=bili_uid)
    return render_to_response("website/templates/settings.html", context=context)


async def post_settings(request):
    bili_uid = await check_login(request)
    if not bili_uid:
        return json_response({"code": 403, "err_msg": "你无权访问。"})

    data = await request.post()
    try:
        tv_percent = int(data["tv_percent"])
        guard_percent = int(data["guard_percent"])
        pk_percent = int(data["pk_percent"])
        storm_percent = int(data["storm_percent"])
        anchor_percent = int(data["anchor_percent"])
        medals = [m.strip() for m in data["medals"].split("\r\n")]
        medals = [m for m in medals if m]
    except (KeyError, TypeError, ValueError) as e:
        return json_response({"code": 403, "err_msg": f"你提交了不正确的参数 ！{e}\n{traceback.format_exc()}"})

    if (
        not 0 <= tv_percent <= 100
        or not 0 <= guard_percent <= 100
        or not 0 <= pk_percent <= 100
        or not 0 <= storm_percent <= 100
        or not 0 <= anchor_percent <= 100
    ):
        return json_response({"code": 403, "err_msg": "范围错误！请设置0~100 ！"})

    for m in medals:
        if not isinstance(m, str) or not 0 < len(m) <= 6:
            return json_response({"code": 403, "err_msg": f"错误的勋章：{m}"})

    await LTUserSettings.set(
        uid=bili_uid,
        tv_percent=tv_percent,
        guard_percent=guard_percent,
        pk_percent=pk_percent,
        storm_percent=storm_percent,
        anchor_percent=anchor_percent,
        medals=medals,
    )
    return json_response({"code": 0})


async def trends_qq_notice(request):
    token = request.query.get("token")
    if token != "BXzgeJTWxGtd6b5F":
        return web.Response(status=403)

    post_data = request.query.get("post_data")
    uid_to_dynamic = json.loads(post_data, encoding="utf-8")

    async def report_error(m):
        # await async_zy.send_private_msg(user_id=g.QQ_NUMBER_雨声雷鸣, message=m)
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=m)

    for uid, dynamic_id_list in uid_to_dynamic.items():
        uid = int(uid)
        dynamic_id_set = set(dynamic_id_list)

        key = f"MONITOR_BILI_UID_V2_{uid}"
        existed_dynamic_id_set = await redis_cache.get(key=key)
        if not isinstance(existed_dynamic_id_set, set):
            await redis_cache.set(key=key, value=dynamic_id_set)

            bili_user_name = await BiliApi.get_user_name(uid=uid)
            m = f"{bili_user_name}(uid: {uid})的动态监测已经添加！"
            await async_zy.send_private_msg(user_id=g.QQ_NUMBER_雨声雷鸣, message=m)
            continue

        new_dynamics = dynamic_id_set - existed_dynamic_id_set
        if not new_dynamics:
            continue

        refreshed_data = dynamic_id_set | existed_dynamic_id_set
        await redis_cache.set(key=key, value=refreshed_data)

        latest_dynamic_id = dynamic_id_list[0]
        flag, dynamic = None, None
        for _try_times in range(3):
            flag, dynamic = await BiliApi.get_dynamic_detail(dynamic_id=latest_dynamic_id)
            if flag:
                break
            await asyncio.sleep(2)

        if not flag:
            await report_error(f"尝试了3次后，也未能获取到动态：{latest_dynamic_id}：{dynamic}")
            continue

        master_name = dynamic["desc"]["user_profile"]["info"]["uname"]
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(dynamic["desc"]["timestamp"]))
        prefix = f"{timestamp}　{master_name}最新发布：\n\n"

        content, pictures = None, None
        for _try_times in range(3):
            content, pictures = await BiliApi.get_user_dynamic_content_and_pictures(dynamic)
            if content or pictures:
                break
            await asyncio.sleep(2)

        if not pictures:
            qq_response = prefix + "\n".join(content)
        else:
            work_path = f"/tmp/bili_dynamic_{int(time.time())}"
            if not os.path.exists(work_path):
                os.mkdir(work_path)

            index = 0
            last_pic_name = None
            for pic in pictures:
                ex_name = pic.split(".")[-1]
                last_pic_name = f"{index}.{ex_name}"
                cmd = f"wget -O {work_path}/{last_pic_name} \"{pic}\""
                os.system(cmd)
                index += 1

            if index > 1:
                p = DynamicPicturesProcessor(path=work_path)
                flag, file_name = p.join()
                if not flag:
                    await report_error(f"处理动态图片时，发生错误（已忽略）：{file_name}")
            else:
                flag = True
                file_name = f"b_{int(time.time() * 1000):0x}." + last_pic_name.split(".")[-1]
                os.system(f"mv {work_path}/{last_pic_name} /home/ubuntu/coolq_zy/data/image/{file_name}")

            if flag:
                message = prefix + "\n".join(content)
                qq_response = f"{message}\n [CQ:image,file={file_name}]"
            else:
                qq_response = prefix + "\n".join(content) + "\n" + "\n".join(pictures)
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_雨声雷鸣, message=qq_response)

    return web.Response(status=206)
