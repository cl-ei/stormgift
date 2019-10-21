import time
import json
import copy
import datetime
import traceback
from random import randint
from aiohttp import web
from jinja2 import Template
from config import CDN_URL
from utils.cq import bot_zy, bot
from utils.biliapi import BiliApi
from utils.dao import redis_cache, HansyDynamicNotic, LTUserSettings
from utils.db_raw_query import AsyncMySQL
from utils.highlevel_api import DBCookieOperator, ReqFreLimitApi
from utils.dao import LtUserLoginPeriodOfValidity


class Cache:
    e_tag = 0
    data = None

    raffle_e_tag = 0
    raffle_data = None


def request_frequency_control(time_interval=4):
    user_requests_records = []  # [(uniq, time), ... ]

    def deco(f):
        async def wrapped(request):
            host = request.headers.get("Host", "governors")
            ua = request.headers.get("User-Agent", "NON_UA")
            unique_identification = hash((host, ua))

            last_req_time = 0
            for _ in user_requests_records:
                if _[0] == unique_identification:
                    last_req_time = _[1]
                    break

            if time.time() - last_req_time < time_interval:
                return web.Response(text=f"拒绝服务：你的请求过于频繁。请{time_interval}秒钟后再试。", content_type="text/html")

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
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/website_homepage.html", context=context)


async def login(request):
    data = await request.post()
    account = data['account']
    password = data['password']
    email = data["email"]
    if not account or not password:
        return json_response({"code": 403, "err_msg": "输入错误！检查你的输入!"})

    try:
        flag, obj = await DBCookieOperator.add_cookie_by_account(
            account=account, password=password, notice_email=email)
    except Exception as e:
        return json_response({"code": 500, "err_msg": f"服务器内部发生错误! {e}\n{traceback.format_exc()}"})

    if not flag:
        return json_response({"code": 403, "err_msg": f"操作失败！原因：{obj}"})

    await LtUserLoginPeriodOfValidity.update(obj.DedeUserID)

    key = f"LT_USER_MAD_TOKEN_{obj.DedeUserID}"
    mad_token = f"{int(time.time() * 1000):0x}{randint(0x1000, 0xffff):0x}"
    await redis_cache.set(key=key, value=mad_token, timeout=3600*24*30)

    response = json_response({"code": 0, "location": "/lt/settings"})
    response.set_cookie(name="mad_token", value=mad_token, httponly=True)
    response.set_cookie(name="DedeUserID", value=obj.DedeUserID, httponly=True)
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
    except (KeyError, TypeError, ValueError):
        return json_response({"code": 403, "err_msg": "你提交了不正确的参数 ！"})

    if (
        not 0 <= tv_percent <= 100
        or not 0 <= guard_percent <= 100
        or not 0 <= pk_percent <= 100
        or not 0 <= storm_percent <= 100
    ):
        return json_response({"code": 403, "err_msg": "范围错误！请设置0~100 ！"})

    await LTUserSettings.set(
        uid=bili_uid,
        tv_percent=tv_percent,
        guard_percent=guard_percent,
        pk_percent=pk_percent,
        storm_percent=storm_percent
    )
    return json_response({"code": 0})


async def query_gifts(request):
    json_req = request.query.get("json")
    start_time = time.time()
    db_query_time = 0

    if time.time() < Cache.e_tag + 10:
        records = Cache.data
    else:
        try:
            db_start_time = time.time()
            raffle_records = await AsyncMySQL.execute(
                (
                    "select id, room_id, gift_name, sender_name, expire_time "
                    "from raffle where expire_time > %s order by id desc;"
                ), (datetime.datetime.now(), )
            )
            guard_records = await AsyncMySQL.execute(
                (
                    "select id, room_id, gift_name, sender_name, expire_time "
                    "from guard where expire_time > %s;"
                ), (datetime.datetime.now(),)
            )
            room_id_list = [row[1] for row in guard_records + raffle_records]
            room_info = await AsyncMySQL.execute(
                (
                    "select name, short_room_id, real_room_id "
                    "from biliuser where real_room_id in %s;"
                ), (room_id_list, )
            )
            room_dict = {}
            for row in room_info:
                name, short_room_id, real_room_id = row
                room_dict[real_room_id] = (name, short_room_id)

            def get_price(g):
                price_map = {
                    "小电视飞船": 1250,
                    "任意门": 600,
                    "幻乐之声": 520,
                    "摩天大楼": 450,
                    "总督": -1,
                    "提督": -2,
                    "舰长": -3
                }
                return price_map.get(g, 0)

            records = []
            for row in raffle_records + guard_records:
                raffle_id, room_id, gift_name, sender_name, expire_time = row
                master_name, short_room_id = room_dict.get(room_id, (None, None))
                if short_room_id == room_id:
                    short_room_id = "-"

                records.append({
                    "gift_name": gift_name.replace("抽奖", ""),
                    "short_room_id": short_room_id,
                    "real_room_id": room_id,
                    "master_name": master_name,
                    "sender_name": sender_name,
                    "raffle_id": raffle_id,
                    "expire_time": expire_time,
                })
            records.sort(key=lambda x: (get_price(x["gift_name"]), x["real_room_id"]), reverse=True)
            db_query_time = time.time() - db_start_time

        except Exception as e:
            msg = F"Error: {e} {traceback.format_exc()}"
            if json_req:
                text = json.dumps({"code": 500, "msg": msg})
                content_type = "application/json"
            else:
                text = msg
                content_type = "text/html"
            return web.Response(text=text, content_type=content_type)

        else:
            Cache.e_tag = time.time()
            Cache.data = records

    if json_req:
        json_result = [
            {
                k: str(v) if isinstance(v, datetime.datetime) else v
                for k, v in r.items()
                if k in ("gift_name", "real_room_id", "raffle_id", "expire_time")
            }
            for r in records
        ]
        return web.Response(
            text=json.dumps(
                {"code": 0, "e_tag": f"{hash(Cache.e_tag):0x}", "list": json_result},
                indent=2,
                ensure_ascii=False,
            ),
            content_type="application/json"
        )

    context = {
        "e_tag": f"{hash(Cache.e_tag):0x}",
        "records": records,
        "proc_time": f"{(time.time() - start_time):.3f}",
        "db_query_time": f"{db_query_time:.3f}",
    }
    return render_to_response("website/templates/website_query_gifts.html", context=context)


async def query_raffles(request):
    json_req = request.query.get("json")

    if time.time() < Cache.raffle_e_tag + 300:
        raffle_data = Cache.raffle_data
    else:
        start_date = datetime.datetime.now() - datetime.timedelta(hours=48)
        records = await AsyncMySQL.execute(
            (
                "select id, room_id, gift_name, gift_type, sender_obj_id, winner_obj_id, "
                "   prize_gift_name, expire_time, sender_name, winner_name "
                "from raffle "
                "where expire_time >= %s "
                "order by id desc ;"
            ), (start_date, )
        )
        user_obj_id_list = []
        room_id_list = []
        for row in records:
            (
                id, room_id, gift_name, gift_type, sender_obj_id, winner_obj_id,
                prize_gift_name, expire_time, sender_name, winner_name
            ) = row

            room_id_list.append(room_id)
            user_obj_id_list.append(sender_obj_id)
            user_obj_id_list.append(winner_obj_id)

        users = await AsyncMySQL.execute(
            (
                "select id, uid, name, short_room_id, real_room_id "
                "from biliuser "
                "where id in %s or real_room_id in %s "
                "order by id desc ;"
            ), (user_obj_id_list, room_id_list)
        )
        room_id_map = {}
        user_obj_id_map = {}
        for row in users:
            id, uid, name, short_room_id, real_room_id = row
            if short_room_id and real_room_id:
                room_id_map[real_room_id] = (short_room_id, name)
            user_obj_id_map[id] = (uid, name)

        raffle_data = []
        for row in records:
            (
                id, real_room_id, gift_name, gift_type, sender_obj_id, winner_obj_id,
                prize_gift_name, expire_time, sender_name, winner_name
            ) = row

            short_room_id, master_uname = room_id_map.get(real_room_id, (None, ""))
            if short_room_id is None:
                short_room_id = ""
            elif short_room_id == real_room_id:
                short_room_id = "-"

            user_id, user_name = user_obj_id_map.get(winner_obj_id, ("", winner_name))
            sender_uid, sender_name = user_obj_id_map.get(sender_obj_id, ("", sender_name))

            info = {
                "short_room_id": short_room_id,
                "real_room_id": real_room_id,
                "raffle_id": id,
                "gift_name": (gift_name.replace("抽奖", "") + "-" + gift_type) or "",
                "prize_gift_name": prize_gift_name or "",
                "created_time": expire_time,
                "user_id": user_id or "",
                "user_name": user_name or "",
                "master_uname": master_uname or "",
                "sender_uid": sender_uid or "",
                "sender_name": sender_name or "",
            }
            raffle_data.append(info)

        Cache.raffle_data = raffle_data
        Cache.raffle_e_tag = time.time()

    if json_req:
        json_result = copy.deepcopy(raffle_data)
        for info in json_result:
            for k, v in info.items():
                if isinstance(v, datetime.datetime):
                    info[k] = str(v)
                elif v == "":
                    info[k] = None

        return web.Response(
            text=json.dumps(
                {"code": 0, "e_tag": f"{hash(Cache.raffle_e_tag):0x}", "list": json_result},
                indent=2,
                ensure_ascii=False,
            ),
            content_type="application/json"
        )

    context = {
        "e_tag": f"{hash(Cache.raffle_e_tag):0x}",
        "raffle_data": raffle_data,
        "raffle_count": len(raffle_data),
        "CDN_URL": CDN_URL,
    }
    return render_to_response("website/templates/website_query_raffles.html", context=context)


@request_frequency_control(time_interval=4)
async def query_raffles_by_user(request):
    uid = request.query.get("uid")
    day_range = request.query.get("day_range")
    now = datetime.datetime.now()
    raffle_start_record_time = now.replace(year=2019, month=7, day=2, hour=0, minute=0, second=0, microsecond=0)

    try:
        day_range = int(day_range)
        assert day_range > 1
    except (ValueError, TypeError, AssertionError):
        return web.Response(text="day_range参数错误。", content_type="text/html")

    end_date = now - datetime.timedelta(days=day_range)
    if end_date < raffle_start_record_time:
        total_days = int((now - raffle_start_record_time).total_seconds() / 3600 / 24)
        return web.Response(
            text=f"day_range参数超出范围。最早可以查询2019年7月2日之后的记录，day_range范围 1 ~ {total_days}。",
            content_type="text/html"
        )

    if not uid or len(uid) > 50:
        return web.Response(text="请输入正确的用户。", content_type="text/html")

    try:
        uid = int(uid)
    except (TypeError, ValueError):
        uid = await ReqFreLimitApi.get_uid_by_name(user_name=uid)

    user_record = await AsyncMySQL.execute(
        "select id, uid, name from biliuser where uid = %s;", (uid, )
    )
    if not user_record:
        return web.Response(text="未收录该用户。", content_type="text/html")

    winner_obj_id, uid, user_name = user_record[0]
    records = await AsyncMySQL.execute(
        (
            "select room_id, prize_gift_name, expire_time, sender_name, id from raffle "
            "where winner_obj_id = %s and expire_time > %s "
            "order by expire_time desc ;"
        ), (winner_obj_id, datetime.datetime.now() - datetime.timedelta(days=day_range))
    )
    if not records:
        return web.Response(text=f"用户{uid} - {user_name} 在{day_range}天内没有中奖。", content_type="text/html")
    room_id_list = [row[0] for row in records]
    room_info = await AsyncMySQL.execute(
        (
            "select short_room_id, real_room_id, name "
            "from biliuser where real_room_id in %s;"
        ), (room_id_list, )
    )
    room_dict = {}
    for row in room_info:
        short_room_id, real_room_id, name = row
        room_dict[real_room_id] = (short_room_id, name)

    raffle_data = []
    for row in records:
        room_id, prize_gift_name, expire_time, sender_name, raffle_id = row
        short_room_id, master_name = room_dict.get(room_id, ("-", None))
        if short_room_id == room_id:
            short_room_id = "-"
        info = {
            "short_room_id": short_room_id,
            "real_room_id": room_id,
            "raffle_id": raffle_id,
            "prize_gift_name": prize_gift_name,
            "sender_name": sender_name,
            "expire_time": expire_time,
            "master_name": master_name,
        }
        raffle_data.insert(0, info)

    context = {
        "uid": uid,
        "user_name": user_name,
        "day_range": day_range,
        "raffle_data": raffle_data,
    }
    return render_to_response("website/templates/website_query_raffles_by_user.html", context=context)


async def trends_qq_notice(request):
    token = request.query.get("token")
    if token == "BXzgeJTWxGtd6b5F":
        post_data = request.query.get("post_data")
        uid_to_dynamic = json.loads(post_data, encoding="utf-8")
        for uid, dynamic_id_list in uid_to_dynamic.items():
            uid = int(uid)
            dynamic_id_set = set(dynamic_id_list)

            key = f"MONITOR_BILI_UID_V2_{uid}"
            existed_dynamic_id_set = await redis_cache.get(key=key)
            if not isinstance(existed_dynamic_id_set, set):
                await redis_cache.set(key=key, value=dynamic_id_set)

                bili_user_name = await BiliApi.get_user_name(uid=uid)
                message = f"{bili_user_name}(uid: {uid})的动态监测已经添加！"
                bot_zy.send_private_msg(user_id=171660901, message=message)
                bot_zy.send_private_msg(user_id=80873436, message=message)
                return web.Response(status=206)

            new_dynamics = dynamic_id_set - existed_dynamic_id_set
            if new_dynamics:
                refreshed_data = dynamic_id_set | existed_dynamic_id_set
                await redis_cache.set(key=key, value=refreshed_data)

                try:
                    flag, dynamics = await BiliApi.get_user_dynamics(uid=uid)
                    if not flag:
                        raise Exception(f"Cannot get user dynamics!")

                    latest_dynamic = dynamics[0]
                    bili_user_name = latest_dynamic["desc"]["user_profile"]["info"]["uname"]
                    content, pictures = await BiliApi.get_user_dynamic_content_and_pictures(latest_dynamic)

                    content = "\n".join(content)
                    message = f"{bili_user_name}(uid: {uid})新动态：\n\n{content}"

                    if uid == 337052615:
                        bot_zy.send_private_msg(user_id=250666570, message=f"#方舟{latest_dynamic}")

                    if not pictures:
                        image = "https://i0.hdslb.com/bfs/space/cb1c3ef50e22b6096fde67febe863494caefebad.png"
                    else:
                        image = pictures[0]

                    message_share = (
                        f"\n\n[CQ:share,"
                        f"url=https://t.bilibili.com/{dynamic_id_list[0]},"
                        f"title={content[:30].replace(',', '，')},content=Bilibili动态,image={image}]"
                    )
                    bot_zy.send_private_msg(user_id=171660901, message=message_share)
                    bot_zy.send_private_msg(user_id=80873436, message=message_share)

                except Exception as e:
                    error_msg = f"Error happened when fetching user dynamic: {e}\n\n{traceback.format_exc()}"
                    bot_zy.send_private_msg(user_id=80873436, message=error_msg)

                    bili_user_name = await BiliApi.get_user_name(uid=uid)
                    message = f"{bili_user_name}(uid: {uid})有新动态啦! 动态id：{dynamic_id_list[0]}！"

                bot_zy.send_private_msg(user_id=171660901, message=message)
                bot_zy.send_private_msg(user_id=80873436, message=message)

        return web.Response(status=206)
    return web.Response(status=403)


async def raffle_broadcast(request):
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/raffle_broadcast.html", context=context)
