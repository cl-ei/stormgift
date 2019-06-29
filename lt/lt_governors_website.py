import time
import json
import traceback
import datetime
from aiohttp import web
from utils.model import objects, GiftRec, User, RaffleRec


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
    records = None
    version = 0


async def get_records_of_raffle(request):
    uid = request.query.get("uid")
    day_range = request.query.get("day_range", 7)
    try:
        uid_list = [int(u.strip()) for u in uid.split("_")]
        assert uid_list

        day_range = int(day_range)
        assert 1 <= day_range <= 180
    except (TypeError, ValueError, AssertionError):
        return web.Response(
            text=json.dumps({"code": 400, "msg": f"Error query param!"}, indent=2, ensure_ascii=False),
            content_type="application/json"
        )

    await objects.connect()
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
                (RaffleRec.user_obj_id.in_(user_obj_id_map.keys()))
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
        records = F"Internal Server Error!"

    finally:
        await objects.close()

    if isinstance(records, str):
        text = json.dumps({"code": 500, "msg": records})
        content_type = "application/json"
        return web.Response(text=text, content_type=content_type)
    response = {"code": 0, "data": records.values()}
    return web.Response(text=json.dumps(response, indent=2, ensure_ascii=False), content_type="application/json")


async def query_gifts(request):
    json_req = request.query.get("json")
    start_time = time.time()

    if time.time() < Cache.version + 30:
        records = Cache.records
    else:
        await objects.connect()
        try:
            records = await objects.execute(GiftRec.select(
                GiftRec.room_id,
                GiftRec.gift_id,
                GiftRec.gift_name,
                GiftRec.expire_time,
                GiftRec.sender,
            ).where(
                GiftRec.expire_time > datetime.datetime.now()
            ))
            records = [
                [r.gift_name, r.room_id, r.gift_id, r.expire_time, r.sender.name] for r in records
            ]
            records.sort(key=lambda x: (gift_price_map.get(x[0], 0), x[1], x[3]), reverse=True)
        except Exception as e:
            records = F"Error: {e} {traceback.format_exc()}"
        finally:
            await objects.close()

        if isinstance(records, str):
            if json_req:
                text = json.dumps({"code": 500, "msg": records})
                content_type = "application/json"
            else:
                text = records
                content_type = "text/html"
            return web.Response(text=text, content_type=content_type)
        else:
            Cache.version = time.time()
            Cache.records = records

    if json_req:
        gift_list = [
            {"gift_name": r[0], "real_room_id": r[1], "raffle_id": r[2], "expire_time": f"{r[3]}"}
            for r in records
        ]
        return web.Response(
            text=json.dumps(
                {"code": 0, "version": hash(Cache.version), "list": gift_list},
                indent=2,
                ensure_ascii=False,
            ),
            content_type="application/json"
        )

    gift_list = [
        (
            f"<tr>"
            f"<th>{r[0]}</th><th>{r[1]}</th><th>{r[4]}</th><th>{r[2]}</th><th>{r[3]}</th>"
            f'<th><a href="https://live.bilibili.com/{r[1]}" target="_blank">Gooo</a></th>'
            f'<th><a href="bilibili://live/{r[1]}" target="_blank">打开破站</a></th>'
            f'</tr>'
        ) for r in records
    ]

    proc_time = time.time() - start_time
    text = (
        f'<html><body><h2>礼物列表:（Version: {hash(Cache.version)}）'
        f'<a href="/query_gifts?json=true" target="_blank">JSON格式</a>'
        f'</h2><table border="1"><tr>'
        f'<th>礼物名称</th>'
        f'<th>原房间号</th>'
        f'<th>赠送者</th>'
        f'<th>raffle id</th>'
        f'<th>失效时间</th>'
        f'<th>传送门</th>'
        f'<th>爪机</th>'
        f'</tr>'
        f"{''.join(gift_list)}"
        f"</table>"
        f"<h6>Process time: {proc_time:.3f}</h6>"
        f"</body></html>"
    )
    return web.Response(text=text, content_type="text/html")


app = web.Application()
app.add_routes([
    web.get('/query_gifts', query_gifts),
    web.get('/get_records_of_raffle', get_records_of_raffle)
])
web.run_app(app, port=2048)
