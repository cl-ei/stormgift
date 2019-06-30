import time
import json
import jinja2
import traceback
import datetime
from aiohttp import web
from utils.model import GiftRec, User, RaffleRec
from utils.model import objects as db_objects


gift_price_map = {
    "舰长": 1,
    "提督": 2,
    "总督": 3,
    "小电视飞船抽奖": 1245,
    "幻乐之声抽奖": 520,
    "任意门抽奖": 520,
    "摩天大楼抽奖": 450,
}


class Cache:
    version = 0
    data = None

    last_time_of_get_raffle = time.time()


class objects:

    _objects = None

    @classmethod
    async def execute(cls, *args, **kwargs):
        if cls._objects is None:
            await db_objects.connect()
            cls._objects = db_objects
        return await cls._objects.execute(*args, **kwargs)


async def get_records_of_raffle(request):
    try:
        uid = request.query.get("uid")
        day_range = request.query.get("day_range", 7)

        uid_list = [int(u.strip()) for u in uid.split("_")]
        assert uid_list

        day_range = int(day_range)
        assert 1 <= day_range <= 180
    except (TypeError, ValueError, AssertionError, AttributeError):
        return web.Response(
            text=json.dumps({"code": 400, "msg": f"Error query param!"}, indent=2, ensure_ascii=False),
            content_type="application/json"
        )

    if time.time() - Cache.last_time_of_get_raffle < 3:
        return web.Response(
            text=json.dumps({"code": 500, "msg": f"System busy!"}, indent=2, ensure_ascii=False),
            content_type="application/json"
        )

    try:
        records = {uid: {"uid": uid, "uname": None, "raffle": []} for uid in uid_list}

        user_objs = await objects.execute(User.select().where(User.uid.in_(uid_list)))
        q = {o.uid: {"uid": o.uid, "uname": o.name, "raffle": []} for o in user_objs}
        records.update(q)

        user_obj_id_map = {u.id: u.uid for u in user_objs}
        raffles = await objects.execute(
            RaffleRec.select(
                RaffleRec.room_id,
                RaffleRec.gift_name,
                RaffleRec.user_obj_id,
                RaffleRec.created_time,
            ).where(
                (RaffleRec.user_obj_id.in_(list(user_obj_id_map.keys())))
                & (RaffleRec.created_time > datetime.datetime.now() - datetime.timedelta(days=day_range))
            )
        )

        for r in raffles:
            uid = user_obj_id_map[r.user_obj_id]
            records[uid]["raffle"].append({
                "real_room_id": r.room_id,
                "gift_name": r.gift_name,
                "created_time": str(r.created_time)
            })

    except Exception as e:
        print(f"Error: {e}, {traceback.format_exc()}")
        records = F"Internal Server Error!"

    Cache.last_time_of_get_raffle = time.time()

    if isinstance(records, str):
        text = json.dumps({"code": 500, "msg": records})
        content_type = "application/json"
        return web.Response(text=text, content_type=content_type)
    response = {"code": 0, "day_range": day_range, "data": list(records.values())}
    return web.Response(text=json.dumps(response, indent=2, ensure_ascii=False), content_type="application/json")


async def query_gifts(request):
    json_req = request.query.get("json")
    start_time = time.time()
    db_query_time = 0

    if time.time() < Cache.version + 10:
        records = Cache.data
    else:
        try:
            db_start_time = time.time()
            records = await objects.execute(GiftRec.select(
                GiftRec.room_id,
                GiftRec.gift_id,
                GiftRec.gift_name,
                GiftRec.expire_time,
                GiftRec.sender_id,
            ).where(
                GiftRec.expire_time > datetime.datetime.now()
            ))

            users = await objects.execute(
                User.select(User.id, User.name).where(User.id.in_([g.sender_id for g in records]))
            )
            user_dict = {u.id: u.name for u in users}

            records = [
                {
                    "gift_name": r.gift_name,
                    "raffle_id": r.gift_id,
                    "real_room_id": r.room_id,
                    "expire_time": r.expire_time,
                    "sender_name": user_dict.get(r.sender_id, None),
                    "price": gift_price_map.get(r.gift_name, 0)
                }
                for r in records
            ]
            records.sort(key=lambda r: (r["price"], r["real_room_id"], r["expire_time"]), reverse=True)

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
            Cache.version = time.time()
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
                {"code": 0, "version": hash(Cache.version), "list": json_result},
                indent=2,
                ensure_ascii=False,
            ),
            content_type="application/json"
        )

    template_text = """
        <html>
        <style>
        table{
            width: 100%;
            margin-bottom: 20px;
            border: 1px solid #7a7a7a;
            border-collapse: collapse;
            border-left: none;
            word-break: normal;
            line-height: 30px;
            text-align: center;
        }
        tr, th, td{
            border: 1px solid #7a7a7a;
        }
        </style>
        <body>
        <h2>礼物列表:（Version: {{ version }}）<a href="/query_gifts?json=true" target="_blank">JSON格式</a></h2>
        <table>
        <tr>
        <th>礼物名称</th>
        <th>原房间号</th>
        <th>赠送者</th>
        <th>raffle id</th>
        <th>失效时间</th>
        <th>传送门</th>
        <th>爪机</th>
        </tr>
        {% for r in records %}
        <tr>
            <td>{{ r.gift_name }}</td>
            <td>{{ r.real_room_id }}</td>
            <td>{{ r.sender_name }}</td>
            <td>{{ r.raffle_id }}</td>
            <td>{{ r.expire_time }}</td>
            <td><a href="https://live.bilibili.com/{{ r.real_room_id }}" target="_blank">Gooo</a></td>
            <td><a href="bilibili://live/{{ r.real_room_id }}" target="_blank">打开破站</a></td>
        </tr>
        {% endfor %}
        </table>
        <h6>Process time: {{ proc_time }}(db query time: {{ db_query_time }})</h6></body></html>
    """
    template_text = " ".join(template_text.split())

    context = {
        "version": f"{hash(Cache.version):0x}",
        "records": records,
        "proc_time": f"{(time.time() - start_time):.3f}",
        "db_query_time": f"{db_query_time:.3f}",

    }

    text = jinja2.Template(template_text).render(context)
    return web.Response(text=text, content_type="text/html")


app = web.Application()
app.add_routes([
    web.get('/query_gifts', query_gifts),
    web.get('/get_records_of_raffle', get_records_of_raffle)
])
web.run_app(app, port=2048)
