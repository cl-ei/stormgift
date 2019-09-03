import time
import json
import copy
import datetime
import traceback
from aiohttp import web
from jinja2 import Template
from config import CDN_URL
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


async def lt(request):
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/website_homepage.html", context=context)


async def api(request):
    data = await request.post()

    action = data.get("action")
    if action == "query":
        uid = data['uid']
        try:
            uid = int("".join(uid.split()))
            assert uid > 0
        except (TypeError, ValueError, AssertionError):
            return web.Response(text=f"错误的uid: {uid}, 重新输入!")

        cookie_obj = await DBCookieOperator.get_by_uid(uid)
        if cookie_obj is None:
            return web.Response(text=f"用户（uid: {uid}）尚未配置。")

        if not cookie_obj.available:
            return web.Response(text=f"用户{cookie_obj.name}（uid: {uid}）的登录已过期，请重新登录。")

        most_recently = await AsyncMySQL.execute(
            "select created_time from userrafflerecord where user_id = %s order by created_time desc limit 1;",
            (uid, )
        )
        if most_recently:
            most_recently = most_recently[0][0]
            interval = (datetime.datetime.now() - most_recently).total_seconds()
            if interval > 3600:
                most_recently = f"约{int(interval // 3600)}小时前"
            elif interval > 60:
                most_recently = f"约{int(interval // 60)}分钟前"
            else:
                most_recently = f"{int(interval)}秒前"
        else:
            most_recently = "未查询到记录"

        rows = await AsyncMySQL.execute(
            (
                "select gift_name, count(raffle_id) "
                "from userrafflerecord "
                "where user_id = %s and created_time >= %s "
                "group by gift_name;"
            ), (uid, datetime.datetime.now() - datetime.timedelta(hours=24))
        )
        raffle_result = []
        total_intimacy = 0
        for gift_name, count in rows:
            intimacy_map = {
                "总督": 20,
                "提督": 5,
                "舰长": 1,
                "小电视飞船抽奖": 5,
                "任意门抽奖": 5,
            }
            total_intimacy += intimacy_map.get(gift_name, 1)*count
            raffle_result.append({
                "gift_name": gift_name,
                "count": count
            })
        if (datetime.datetime.now() - cookie_obj.blocked_time).total_seconds() < 3600 * 6:
            blocked_datetime = cookie_obj.blocked_time
        else:
            blocked_datetime = None

        if blocked_datetime:
            title = (
                f"<h3>系统在{str(blocked_datetime)[:19]}发现你被关进了小黑屋</h3>"
                f"<p>目前挂辣条暂停中。稍后会再探测</p>"
                f"<p>最后一次抽奖时间：{str(most_recently)}</p>"
                f"<p>最近24小时内的领奖统计（24小时内累计获得亲密度：{total_intimacy}）：</p>"
            )
        else:
            title = (
                f"<h3>你现在正常领取辣条中</h3>"
                f"<p>最后一次抽奖时间：{str(most_recently)}</p>"
                f"<p>最近24小时内的领奖统计（24小时内累计获得亲密度：{total_intimacy}）：</p>"
            )

        context = {
            "CDN_URL": CDN_URL,
            "query": True,
            "raffle_result": raffle_result,
            "title": title,
        }
        return render_to_response("website/templates/website_homepage.html", context=context)

    elif action == "user_login":
        account = data['account']
        password = data['password']
        email = data["email"]
        if not account or not password:
            return web.Response(text="输入错误！检查你的输入!")
        try:
            flag, obj = await DBCookieOperator.add_cookie_by_account(account=account, password=password, notice_email=email)
        except Exception as e:
            return web.Response(text=f"Internal server error: {e}\n {traceback.format_exc()}")

        if flag:
            await LtUserLoginPeriodOfValidity.update(obj.DedeUserID)
            return web.Response(text=f"用户{obj.name}（uid: {obj.DedeUserID}）配置成功！")
        else:
            return web.Response(text=f"配置失败！原因：{obj}")

    else:
        return web.Response(text=f"X")


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

