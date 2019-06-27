import time
import json
import asyncio
import datetime
from aiohttp import web
from utils.model import objects, GiftRec, User
from peewee_async import select


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


async def query_gifts_json(request):
    response_json = {"a": {"c": [1, 2]}}
    return web.Response(text=json.dumps(response_json, indent=2, ensure_ascii=False), content_type="application/json")


async def query_gifts(request):
    json_req = request.query.get("json")

    if time.time() < Cache.version + 30:
        records = Cache.records
    else:
        await objects.connect()
        records_list = []

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
            records = F"Error: {e}"
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
            text=json.dumps({"code": 0, "version": hash(Cache.version), "list": gift_list}),
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
        f"</table></body></html>"
    )
    return web.Response(text=text, content_type="text/html")


app = web.Application()
app.add_routes([
    web.get('/query_gifts', query_gifts),
    web.get('/query_gifts_json', query_gifts_json)
])
web.run_app(app, port=2048)
