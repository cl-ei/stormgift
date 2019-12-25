import time
import json
import weakref
import asyncio
import datetime
import traceback
from aiohttp import web
from config import config
from random import random
from utils.biliapi import BiliApi
from utils.mq import mq_source_to_raffle
from utils.cq import CQClient, async_zy
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import lt_raffle_id_getter_logger as logging
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor


api_root = config["ml_bot"]["api_root"]
access_token = config["ml_bot"]["access_token"]
ml_qq = CQClient(api_root=api_root, access_token=access_token)


class Worker(object):
    def __init__(self, index, broadcast_target):
        self.index = index
        self.broadcast = broadcast_target

    @staticmethod
    async def record_raffle_info(danmaku, created_time, msg_from_room_id):
        created_time = datetime.datetime.now() - datetime.timedelta(seconds=(time.time() - created_time))

        cmd = danmaku["cmd"]
        if cmd in ("RAFFLE_END", "TV_END"):
            data = danmaku["data"]
            winner_name = data["uname"]
            winner_uid = await ReqFreLimitApi.get_uid_by_name(winner_name)
            winner_face = data["win"]["face"]
            raffle_id = int(data["raffleId"])
            gift_type = data["type"]
            sender_name = data["from"]
            sender_face = data["fromFace"]
            prize_gift_name = data["giftName"]
            prize_count = int(data["win"]["giftNum"])

            raffle = await RedisRaffle.get(raffle_id=raffle_id)
            if not raffle:
                sender_uid = await ReqFreLimitApi.get_uid_by_name(sender_name)
                gift_gen_time = created_time - datetime.timedelta(seconds=180)
                gift_name = await redis_cache.get(key=f"GIFT_TYPE_{gift_type}")

                raffle = {
                    "raffle_id": raffle_id,
                    "room_id": msg_from_room_id,
                    "gift_name": gift_name,
                    "gift_type": gift_type,
                    "sender_uid": sender_uid,
                    "sender_name": sender_name,
                    "sender_face": sender_face,
                    "created_time": gift_gen_time,
                    "expire_time": created_time,
                }

            update_param = {
                "prize_gift_name": prize_gift_name,
                "prize_count": prize_count,
                "winner_uid": winner_uid,
                "winner_name": winner_name,
                "winner_face": winner_face,
                "danmaku_json_str": json.dumps(danmaku),
            }
            raffle.update(update_param)
            await RedisRaffle.add(raffle_id=raffle_id, value=raffle)

        elif cmd == "ANCHOR_LOT_AWARD":
            data = danmaku["data"]
            raffle_id = data["id"]
            data["room_id"] = msg_from_room_id
            await RedisAnchor.add(raffle_id=raffle_id, value=data)

        else:
            return f"RAFFLE_RECORD received error cmd `{danmaku['cmd']}`!"

    async def proc_single_gift_of_guard(self, room_id, gift_info):
        gift_id = gift_info.get('id', 0)
        key = F"G${room_id}${gift_id}"

        if not await redis_cache.set_if_not_exists(key, "de-duplication"):
            return

        privilege_type = gift_info["privilege_type"]
        if privilege_type == 3:
            gift_name = "舰长"
        elif privilege_type == 2:
            gift_name = "提督"
        elif privilege_type == 1:
            gift_name = "总督"
        else:
            gift_name = "guard_%s" % privilege_type

        await self.broadcast(json.dumps({
            "raffle_type": "guard",
            "ts": int(time.time()),
            "real_room_id": room_id,
            "raffle_id": gift_id,
            "gift_name": gift_name,
        }, ensure_ascii=False))

        expire_time = gift_info["created_time"] + datetime.timedelta(seconds=gift_info["time"])
        sender = gift_info["sender"]
        create_param = {
            "gift_id": gift_id,
            "room_id": room_id,
            "gift_name": gift_name,
            "sender_uid": sender["uid"],
            "sender_name": sender["uname"],
            "sender_face": sender["face"],
            "created_time": gift_info["created_time"],
            "expire_time": expire_time,
        }
        await RedisGuard.add(raffle_id=gift_id, value=create_param)

    @staticmethod
    async def proc_tv_gifts_by_single_user(user_name, gift_list):
        uid = await ReqFreLimitApi.get_uid_by_name(user_name, wait_time=1)

        for info in gift_list:
            info["uid"] = uid

            create_param = {
                "raffle_id": info["gift_id"],
                "room_id": info["room_id"],
                "gift_name": info["gift_name"],
                "gift_type": info["gift_type"],
                "sender_uid": uid,
                "sender_name": info["name"],
                "sender_face": info["face"],
                "created_time": info["created_time"],
                "expire_time": info["created_time"] + datetime.timedelta(seconds=info["time"])
            }
            await RedisRaffle.add(raffle_id=info["gift_id"], value=create_param)

    async def proc_single_msg(self, msg):
        created_time = datetime.datetime.now()
        now_ts = time.time()
        key_type, room_id, *danmakus = msg

        if key_type == "R" and danmakus:
            danmaku = danmakus[0]
            created_time = time.time()
            return await self.record_raffle_info(danmaku, created_time, room_id)

        elif key_type == "D":  # 弹幕追踪
            danmaku = danmakus[0]
            info = danmaku.get("info", {})
            msg = str(info[1])
            uid = info[2][0]
            user_name = info[2][1]
            is_admin = info[2][2]
            ul = info[4][0]
            d = info[3]
            dl = d[0] if d else "-"
            deco = d[1] if d else "undefined"
            message = f"{room_id} ->\n\n{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
            logging.info(message)
            await async_zy.send_private_msg(user_id=80873436, message=message)

        elif key_type == "G":
            flag, gift_info_list = await BiliApi.get_guard_raffle_id(room_id)
            if not flag:
                logging.error(f"Guard proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

            for gift_info in gift_info_list:
                gift_info["created_time"] = created_time
                await self.proc_single_gift_of_guard(room_id, gift_info=gift_info)

        elif key_type == "T":
            flag, gift_info_list = await BiliApi.get_tv_raffle_id(room_id)
            if not flag:
                logging.error(f"TV proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

            result = {}
            for info in gift_info_list:
                user_name = info.get("from_user").get("uname")
                gift_id = info.get("raffleId", 0)
                gift_type = info.get("type")
                gift_name = info.get("thank_text", "").split("赠送的", 1)[-1]
                await redis_cache.set(key=f"GIFT_TYPE_{gift_type}", value=gift_name)

                i = {
                    "name": user_name,
                    "face": info.get("from_user").get("face"),
                    "room_id": room_id,
                    "gift_id": gift_id,
                    "gift_name": gift_name,
                    "gift_type": gift_type,
                    "sender_type": info.get("sender_type"),
                    "created_time": created_time,
                    "status": info.get("status"),
                    "time": info.get("time"),
                }
                result.setdefault(user_name, []).append(i)
                key = f"T${room_id}${gift_id}"
                if not await redis_cache.set_if_not_exists(key, "de-duplication"):
                    continue

                await self.broadcast(json.dumps({
                    "raffle_type": "tv",
                    "ts": int(now_ts),
                    "real_room_id": room_id,
                    "raffle_id": gift_id,
                    "gift_name": gift_name,
                    "gift_type": gift_type,
                    "time_wait": info["time_wait"],
                    "max_time": info["max_time"],
                }, ensure_ascii=False))

            for user_name, gift_list in result.items():
                await self.proc_tv_gifts_by_single_user(user_name, gift_list)

        elif key_type == "P" and danmakus:
            danmaku = danmakus[0]
            raffle_id = danmaku["data"]["id"]
            key = f"P${room_id}${raffle_id}"
            if await redis_cache.set_if_not_exists(key, "de-duplication"):
                await self.broadcast(json.dumps({
                    "raffle_type": "pk",
                    "ts": int(now_ts),
                    "real_room_id": room_id,
                    "raffle_id": raffle_id,
                    "gift_name": "PK",
                }, ensure_ascii=False))

        elif key_type == "S":
            await self.broadcast(json.dumps({
                "raffle_type": "storm",
                "ts": int(now_ts),
                "real_room_id": room_id,
                "raffle_id": None,
                "gift_name": "节奏风暴",
            }, ensure_ascii=False))

        elif key_type == "A":
            # require_type = data["require_type"]
            # 0: 无限制; 1: 关注主播; 2: 粉丝勋章; 3大航海； 4用户等级；5主站等级
            danmaku = danmakus[0]

            data = danmaku["data"]
            raffle_id = data["id"]
            room_id = data["room_id"]
            award_name = data["award_name"]
            award_num = data["award_num"]
            cur_gift_num = data["cur_gift_num"]
            gift_name = data["gift_name"]
            gift_num = data["gift_num"]
            gift_price = data["gift_price"]
            join_type = data["join_type"]
            require_type = data["require_type"]
            require_value = data["require_value"]
            require_text = data["require_text"]
            danmu = data["danmu"]

            key = f"A${room_id}${raffle_id}"
            if await redis_cache.set_if_not_exists(key, "de-duplication"):
                # join_type = data["join_type"]
                # if join_type == 0:  # 免费参与
                #
                #     in_black_list = False
                #     for value in (award_name, room_id, danmu):
                #         if await AnchorBlackList.is_include(str(value)):
                #             in_black_list = True
                #             break
                #
                #     if in_black_list:
                #         logging.info(f"Anchor in black list! room_id: {room_id}, award: {award_name}, danmu: {danmu}")
                #     do: join

                await self.broadcast(json.dumps({
                    "raffle_type": "anchor",
                    "ts": int(now_ts),
                    "real_room_id": room_id,
                    "raffle_id": raffle_id,
                    "gift_name": "天选时刻",
                    "join_type": join_type,
                    "require": f"{require_type}-{require_value}:{require_text}",
                    "gift": f"{gift_num}*{gift_name or 'null'}({gift_price})",
                    "award": f"{award_num}*{award_name}",
                }, ensure_ascii=False))

    async def run_forever(self):
        while True:
            msg = await mq_source_to_raffle.get()

            start_time = time.time()
            task_id = f"{int(str(random())[2:]):x}"

            try:
                r = await self.proc_single_msg(msg)
            except Exception as e:
                logging.error(f"RAFFLE Task {self.index}-[{task_id}] error: {e}, {traceback.format_exc()}")
                continue

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.info(f"RAFFLE Task {self.index}-[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.info("-" * 80)
    logging.info("LT PROC_RAFFLE started!")
    logging.info("-" * 80)

    app = web.Application()
    app['ws'] = weakref.WeakSet()

    async def broadcaster(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        request.app['ws'].add(ws)
        try:
            async for msg in ws:
                pass
        finally:
            request.app['ws'].discard(ws)
        return ws

    app.add_routes([web.get('/raffle_wss', broadcaster), ])
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '127.0.0.1', 1024)
    await site.start()
    print("Site started.")

    async def broadcast_target(message):
        logging.info(f"broadcast: {message}")
        for ws in set(app['ws']):
            await ws.send_str(f"{message}\n")

    await asyncio.gather(*[
        asyncio.create_task(Worker(index, broadcast_target).run_forever())
        for index in range(8)
    ])


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
