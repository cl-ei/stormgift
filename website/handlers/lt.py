import os
import time
import json
import aiohttp
import asyncio
import traceback
from aiohttp import web
from random import randint
from jinja2 import Template
from typing import List

from utils.cq import async_zy
from config import CDN_URL, g
from config.log4 import lt_login_logger
from config.log4 import website_logger as logging
from utils.dao import redis_cache
from utils.biliapi import BiliApi
from utils.images import DynamicPicturesProcessor
from src.db.models.cron_action import UserActRec
from src.db.queries.cron_action import get_user_3d_records
from src.db.queries.queries import queries, LTUser
from website.operations import add_user_by_account


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


async def gen_login_succeed_response(lt_user: LTUser):
    key = f"LT_USER_MAD_TOKEN_{lt_user.DedeUserID}"
    mad_token = f"{int(time.time() * 1000):0x}{randint(0x1000, 0xffff):0x}"
    await redis_cache.set(key=key, value=mad_token, timeout=3600*24*30)

    response = json_response({"code": 0, "location": "/lt/settings"})
    response.set_cookie(name="mad_token", value=mad_token)
    response.set_cookie(name="DedeUserID", value=str(lt_user.DedeUserID))
    return response


async def lt(request):
    token = request.match_info['token']
    qr_code = request.query.get("qr_code")
    if not token:
        return web.HTTPForbidden()

    ua = request.headers.get("User-Agent", "NON_UA")
    remote_ip = request.remote  # request.headers.get("X-Real-IP", "")
    logging.info(f"LT_ACCESS_TOKEN_RECEIVED: {token}, ip: {remote_ip}. UA: {ua}")

    key = F"LT_ACCESS_TOKEN_{token}"
    r = await redis_cache.get(key=key, _un_pickle=True)
    if not r:
        return web.HTTPNotFound()
    r = await redis_cache.incr(key)
    if r < 4:
        return web.Response(text="<h3>请刷新此页面，直到能够正常显示。</h3>", content_type="text/html")
    await redis_cache.delete(key)

    context = {
        "CDN_URL": CDN_URL,
        "token": token,
    }
    if not qr_code:
        return render_to_response("website/templates/home.html", context=context)

    url = "https://passport.bilibili.com/qrcode/getLoginUrl"
    async with aiohttp.request("get", url=url, headers=BROWSER_HEADERS) as r:
        bili_response = await r.json()

    context.update({
        "ts": bili_response["ts"],
        "url": bili_response["data"]["url"],
        "oauthKey": bili_response["data"]["oauthKey"],
    })
    return render_to_response("website/templates/qr_code_login.html", context=context)


async def login(request):
    data = await request.post()
    token = data['token']
    account = data['account']
    password = data['password']
    email = data["email"]
    if not account or not password:
        return json_response({"code": 403, "err_msg": "输入错误！检查你的输入!"})

    qq_number = await redis_cache.get(F"LT_TOKEN_TO_QQ:{token}")
    if not qq_number:
        return json_response({
            "code": 403,
            "err_msg": "未能追踪到此页面的来源，请你重新获取。此页面是专属链接，请不要分享给他人。"
        })

    try:
        flag, message = await add_user_by_account(
            account=account,
            password=password,
            notice_email=email,
            bind_qq=qq_number,
        )
    except Exception as e:
        message = f"Error in add_user_by_account: {e}\n{traceback.format_exc()}"
        return json_response({"code": 403, "err_msg": f"操作失败！原因：\n\n{message}"})

    if not flag:
        lt_login_logger.error(f"登录失败: {account}-{password}：{message}")
        return json_response({"code": 403, "err_msg": f"操作失败！原因：{message}"})

    lt_user = message
    response = await gen_login_succeed_response(lt_user)
    lt_login_logger.info(f"登录成功: {account}-{password}：lt. available: {lt_user.available}")
    return response


async def qr_code_result(request):
    oauth_key = request.query.get("oauthKey")
    token = request.query.get("token")
    qq_number = await redis_cache.get(F"LT_TOKEN_TO_QQ:{token}")
    if not qq_number:
        return json_response({
            "code": 400,
            "msg": f"未能追踪到此页面的来源，请重新获取。此页面是专属链接，请不要分享给他人。"
        })

    url = "https://passport.bilibili.com/qrcode/getLoginInfo"
    data = {
        'oauthKey': oauth_key,
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

    lt_user = await queries.upsert_lt_user(
        access_token="",
        refresh_token="",
        bind_qq=qq_number,
        **cookies_dict
    )

    response = await gen_login_succeed_response(lt_user)
    lt_login_logger.info(f"登录成功: DedeUserID: {lt_user}：qrcode")
    return response


async def settings(request):
    context = {"CDN_URL": CDN_URL}
    bili_uid = await check_login(request)
    if not bili_uid:
        context["err_msg"] = "你无权访问此页面。请返回宝藏站点首页，正确填写你的信息，然后点击「我要挂辣条」按钮。"
        return render_to_response("website/templates/settings.html", context=context)

    lt_user = await queries.get_lt_user_by_uid(user_id=bili_uid)
    context["user_name"] = lt_user.name
    context["user_id"] = lt_user.uid
    medals = ["" for _ in range(7)]
    for i, medal in enumerate(lt_user.send_medals):
        if i >= 7:
            break
        medals[i] = medal

    context["send_medals"] = medals
    context["shine_medals"] = lt_user.shine_medals
    context["medal_intimacy_policy"] = lt_user.medal_intimacy_policy
    context["shine_medal_policy"] = lt_user.shine_medal_policy
    context["shine_medal_count"] = lt_user.shine_medal_count
    context["storm_heart"] = lt_user.storm_heart

    return render_to_response("website/templates/settings.html", context=context)


async def post_settings(request):
    bili_uid = await check_login(request)
    if not bili_uid:
        return json_response({"code": 403, "err_msg": "你无权访问。"})

    data = await request.post()
    try:
        send_medals = [m.strip() for m in data["send_medals"].split("\r\n") if m.strip()]
        shine_medals = [m.strip() for m in data["shine_medals"].split("\r\n") if m.strip()]

        medal_intimacy_policy = int(data["medal_intimacy_policy"])
        shine_medal_policy = int(data["shine_medal_policy"])
        shine_medal_count = int(data["shine_medal_count"])
        storm_heart = data["storm_heart"] == "true"
        for m in send_medals + shine_medals:
            if not isinstance(m, str) or not 0 < len(m) <= 6:
                return json_response({"code": 403, "err_msg": f"错误的勋章：{m}"})

        assert 0 <= medal_intimacy_policy <= 2, "自动赠送亲密度的策略错误！"
        assert 0 <= shine_medal_policy <= 3, "自动擦亮勋章的策略错误！"
        if shine_medal_policy == 2:  #
            assert 0 < shine_medal_count < 100, "自动擦亮勋章的数量超出范围！最少为1，最多为99个勋章。"
        else:
            shine_medal_count = 5
        assert 0 <= len(shine_medals) < 100, "自定义擦亮勋章的数量太多！最多可设置99个勋章。"

    except AssertionError as e:
        return json_response({"code": 403, "err_msg": f"你提交了不正确的参数 ！\n{e}"})

    except (KeyError, TypeError, ValueError) as e:
        return json_response({"code": 403, "err_msg": f"你提交了不正确的参数 ！{e}\n{traceback.format_exc()}"})

    lt_user = await queries.get_lt_user_by_uid(bili_uid)
    lt_user.send_medals = send_medals
    lt_user.shine_medals = shine_medals
    lt_user.medal_intimacy_policy = medal_intimacy_policy
    lt_user.shine_medal_policy = shine_medal_policy
    lt_user.shine_medal_count = shine_medal_count
    lt_user.storm_heart = storm_heart

    await queries.update_lt_user(lt_user, fields=(
        "send_medals",
        "shine_medals",
        "medal_intimacy_policy",
        "shine_medal_policy",
        "shine_medal_count",
        "storm_heart",
    ))
    return json_response({"code": 0})


async def act_record(request):
    key = request.match_info['key']
    uid = await redis_cache.get(F"STAT_Q:{key}")
    if not uid:
        return web.Response(status=404)

    user = await queries.get_lt_user_by_uid(uid)
    act_list: List[UserActRec] = await get_user_3d_records(user.user_id)
    print("act_list[1].send_gift: ", act_list[1].send_gift)
    context = {
        "CDN_URL": CDN_URL,
        "user": user,
        "act_list": act_list,
    }
    return render_to_response("website/templates/act_record.html", context=context)


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
