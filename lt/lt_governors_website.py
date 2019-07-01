import time
import json
import copy
import jinja2
import traceback
import datetime
from aiohttp import web
from utils.model import GiftRec, User, RaffleRec, LiveRoomInfo
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
    e_tag = 0
    data = None

    raffle_e_tag = 0
    raffle_data = None

    last_time_of_get_raffle = time.time()
    last_time_of_query_raffles_by_user = time.time()


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

    if time.time() < Cache.e_tag + 10:
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

            live_room_info = await objects.execute(
                LiveRoomInfo.select(LiveRoomInfo.short_room_id, LiveRoomInfo.real_room_id).where(
                    LiveRoomInfo.real_room_id.in_([g.room_id for g in records])
                )
            )
            live_room_dict = {l.real_room_id: l.short_room_id for l in live_room_info}

            def get_short_live_room_id(real_room_id):
                short_room_id = live_room_dict.get(real_room_id)
                if short_room_id is None:
                    return ""
                else:
                    if short_room_id == real_room_id:
                        return "-"
                    else:
                        return short_room_id

            records = [
                {
                    "gift_name": r.gift_name,
                    "raffle_id": r.gift_id,
                    "short_room_id": get_short_live_room_id(r.room_id),
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

    template_text = """
        <html>
        <style>
        table{
            width: 100%;
            max-width: 1100px;
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
        <h2>礼物列表:（e_tag: {{ e_tag }}）<a href="/query_gifts?json=true" target="_blank">JSON格式</a></h2>
        <table>
        <tr>
        <th>礼物名称</th>
        <th>短房间号</th>
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
            <td>{{ r.short_room_id }}</td>
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
        "e_tag": f"{hash(Cache.e_tag):0x}",
        "records": records,
        "proc_time": f"{(time.time() - start_time):.3f}",
        "db_query_time": f"{db_query_time:.3f}",
    }

    text = jinja2.Template(template_text).render(context)
    return web.Response(text=text, content_type="text/html")


async def query_raffles(request):
    json_req = request.query.get("json")

    if time.time() < Cache.raffle_e_tag + 300:
        raffle_data = Cache.raffle_data
    else:
        records = await objects.execute(RaffleRec.select(
            RaffleRec.room_id,
            RaffleRec.raffle_id,
            RaffleRec.gift_name,
            RaffleRec.user_obj_id,
            RaffleRec.created_time,
        ).where(
            RaffleRec.created_time > (datetime.datetime.now() - datetime.timedelta(hours=48))
        ))
        sender_user_obj_id = await objects.execute(
            GiftRec.select(
                GiftRec.gift_id, GiftRec.sender_id
            ).where(
                GiftRec.gift_id.in_([r.raffle_id for r in records])
            )
        )
        live_room_info = await objects.execute(
            LiveRoomInfo.select(
                LiveRoomInfo.short_room_id,
                LiveRoomInfo.real_room_id,
                LiveRoomInfo.user_id,
            ).where(
                LiveRoomInfo.real_room_id.in_([g.room_id for g in records])
            )
        )
        live_room_dict = {l.real_room_id: (l.short_room_id, l.user_id) for l in live_room_info}

        users = await objects.execute(
            User.select(User.id, User.uid, User.name).where(
                User.id.in_([r.user_obj_id for r in records] + [s.sender_id for s in sender_user_obj_id])
                | User.uid.in_([r.user_id for r in live_room_info])
            )
        )
        user_dict = {u.id: (u.uid, u.name) for u in users}
        uid_to_uname_dict = {u.uid: u.name for u in users}
        sender_dict = {s.gift_id: user_dict[s.sender_id] for s in sender_user_obj_id}

        raffle_data = []
        for r in records:

            sender_uid, sender_name = sender_dict.get(r.raffle_id, ("", ""))

            this_live_room = live_room_dict.get(r.room_id)
            if this_live_room:
                short_room_id = "-" if this_live_room[0] == r.room_id else this_live_room[0]
                master_uid = this_live_room[1]
                master_uname = uid_to_uname_dict.get(master_uid, "")
            else:
                short_room_id = ""
                master_uname = ""

            info = {
                "short_room_id": short_room_id,
                "real_room_id": r.room_id,
                "raffle_id": r.raffle_id,
                "gift_name": r.gift_name,
                "created_time": r.created_time,
                "user_id": user_dict[r.user_obj_id][0],
                "user_name": user_dict[r.user_obj_id][1],
                "master_uname": master_uname,
                "sender_uid": sender_uid,
                "sender_name": sender_name,
            }
            raffle_data.insert(0, info)
        # result.sort(key=lambda x: x["created_time"])

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

    template_text = """
            <html>
            <style>
            table{
                width: 100%;
                max-width: 1600px;
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
            input{
                text-align: center;
            }
            button{
                border: none;
                background: #ccc;
                padding: 6px 12px;
                margin-top: 15px;
                outline: none;
                transition: all 0.3s ease-out;
                cursor: pointer;
            }button:hover{
                background: #777;
                color: #fff;
            }
            </style>
            <body>
            <h2>中奖记录:（e_tag: {{ e_tag }}）<a href="/query_raffles?json=true" target="_blank">JSON格式</a></h2>
            <p>仅展示48小时内的获奖记录，共计{{ raffle_count }}条。
                <div>
                    精确查询用户中奖记录：
                    <label>uid或用户名<input class="redinput" type="text" name="uid"></label>
                    <label><input class="redinput" type="number" name="day_range" value="7">天内</label>
                    <button class="button center" id="submit-query">查询</button>                    
                </div>
            </p>
            <table>
            <tr>
            <th>raffle id</th>
            <th>短房间号</th>
            <th>原房间号</th>
            <th>主播</th>
            <th>奖品</th>
            <th>获奖用户uid</th>
            <th>获奖用户名</th>
            <th>奖品提供者uid</th>
            <th>奖品提供用户名</th>
            <th>中奖时间</th>
            </tr>
            {% for r in raffle_data %}
            <tr>
                <td>{{ r.raffle_id }}</td>
                <td>{{ r.short_room_id }}</td>
                <td>{{ r.real_room_id }}</td>
                <td>{{ r.master_uname }}</td>
                <td>{{ r.gift_name }}</td>
                <td>{{ r.user_id }}</td>
                <td>{{ r.user_name }}</td>
                <td>{{ r.sender_uid }}</td>
                <td>{{ r.sender_name }}</td>
                <td>{{ r.created_time }}</td>
            </tr>
            {% endfor %}
            </table>
            <script type="text/javascript" src="http://49.234.17.23/static/js/jquery.min.js"></script>
            <script>
                $("#submit-query").click(function(){
                    let uid = $("input[name=uid]").val();
                    let dayRange = parseInt($("input[name=day_range]").val());
                    window.open("/query_raffles_by_user?day_range=" + dayRange + "&uid=" + uid);
                });
            </script>
            </body></html>
        """
    template_text = " ".join(template_text.split())

    context = {
        "e_tag": f"{hash(Cache.raffle_e_tag):0x}",
        "raffle_data": raffle_data,
        "raffle_count": len(raffle_data),
    }

    text = jinja2.Template(template_text).render(context)
    return web.Response(text=text, content_type="text/html")


async def query_raffles_by_user(request):
    uid = request.query.get("uid")
    day_range = request.query.get("day_range")

    try:
        day_range = int(day_range)
        assert 0 < day_range < 180
    except Exception:
        return web.Response(text="day_range参数错误。1~180天", content_type="text/html")

    if not uid or len(uid) > 50:
        return web.Response(text="请输入正确的用户。", content_type="text/html")

    if time.time() - Cache.last_time_of_query_raffles_by_user < 4:
        return web.Response(text="系统繁忙。", content_type="text/html")
    Cache.last_time_of_query_raffles_by_user = time.time()

    try:
        uid = int(uid)
    except Exception:
        user_objs = await objects.execute(User.select(User.id, User.uid, User.name).where(User.name == uid))
    else:
        user_objs = await objects.execute(User.select(User.id, User.uid, User.name).where(User.uid == uid))

    if not user_objs:
        return web.Response(text="未查询到记录。", content_type="text/html")

    user_obj = user_objs[0]
    records = await objects.execute(RaffleRec.select(
        RaffleRec.room_id,
        RaffleRec.raffle_id,
        RaffleRec.gift_name,
        RaffleRec.created_time,
    ).where(
        (RaffleRec.created_time > (datetime.datetime.now() - datetime.timedelta(days=day_range)))
        & (RaffleRec.user_obj_id == user_obj.id)
    ))
    if not records:
        return web.Response(text="未查询到记录。", content_type="text/html")

    live_room_info = await objects.execute(
        LiveRoomInfo.select(
            LiveRoomInfo.short_room_id,
            LiveRoomInfo.real_room_id,
            LiveRoomInfo.user_id,
        ).where(
            LiveRoomInfo.real_room_id.in_([g.room_id for g in records])
        )
    )
    live_room_dict = {l.real_room_id: (l.short_room_id, l.user_id) for l in live_room_info}

    users = await objects.execute(
        User.select(User.id, User.uid, User.name).where(
            User.uid.in_([r.user_id for r in live_room_info])
        )
    )
    uid_to_uname_dict = {u.uid: u.name for u in users}

    raffle_data = []
    for r in records:
        this_live_room = live_room_dict.get(r.room_id)
        if this_live_room:
            short_room_id = "-" if this_live_room[0] == r.room_id else this_live_room[0]
            master_uid = this_live_room[1]
            master_uname = uid_to_uname_dict.get(master_uid, "")
        else:
            short_room_id = ""
            master_uname = ""

        info = {
            "short_room_id": short_room_id,
            "real_room_id": r.room_id,
            "raffle_id": r.raffle_id,
            "gift_name": r.gift_name,
            "created_time": r.created_time,
            "master_uname": master_uname,
        }
        raffle_data.insert(0, info)

    template_text = """
            <html>
            <style>
            table{
                width: 100%;
                max-width: 1100px;
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
            input{
                text-align: center;
            }
            </style>
            <body>
            <h2>用户uid: {{ uid }} - {{ user_name }} 在{{ day_range }}天内获奖列表: </h2>
            <table>
            <tr>
            <th>raffle id</th>
            <th>短房间号</th>
            <th>原房间号</th>
            <th>主播</th>
            <th>奖品</th>
            <th>中奖时间</th>
            </tr>
            {% for r in raffle_data %}
            <tr>
                <td>{{ r.raffle_id }}</td>
                <td>{{ r.short_room_id }}</td>
                <td>{{ r.real_room_id }}</td>
                <td>{{ r.master_uname }}</td>
                <td>{{ r.gift_name }}</td>
                <td>{{ r.created_time }}</td>
            </tr>
            {% endfor %}
            </table>
            </body></html>
        """
    template_text = " ".join(template_text.split())

    context = {
        "uid": user_obj.id,
        "user_name": user_obj.name,
        "day_range": day_range,
        "raffle_data": raffle_data,
    }

    text = jinja2.Template(template_text).render(context)
    return web.Response(text=text, content_type="text/html")


app = web.Application()
app.add_routes([
    web.get('/query_gifts', query_gifts),
    web.get('/query_raffles', query_raffles),
    web.get('/query_raffles_by_user', query_raffles_by_user),
    web.get('/get_records_of_raffle', get_records_of_raffle)
])
web.run_app(app, port=2048)
