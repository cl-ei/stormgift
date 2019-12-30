import time
import json
import weakref
import asyncio
import datetime
import traceback
from config import g
from aiohttp import web
from utils.cq import async_zy
from utils.biliapi import BiliApi
from utils.udp import mq_source_to_raffle
from config.log4 import lt_server_logger as logging
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor, InLotteryLiveRooms


class Executor:
    def __init__(self, start_time, br):
        self._start_time = start_time
        self.broadcast = br

    async def r(self, *args):
        """ record_raffle """

        key_type, room_id, danmaku, *_ = args
        cmd = danmaku["cmd"]

        if cmd == "ANCHOR_LOT_AWARD":
            data = danmaku["data"]
            raffle_id = data["id"]
            data["room_id"] = room_id
            await RedisAnchor.add(raffle_id=raffle_id, value=data)

        elif cmd in ("RAFFLE_END", "TV_END"):
            data = danmaku["data"]
            winner_name = data["uname"]
            winner_uid = None
            winner_face = data["win"]["face"]
            raffle_id = int(data["raffleId"])
            gift_type = data["type"]
            sender_name = data["from"]
            sender_face = data["fromFace"]
            prize_gift_name = data["giftName"]
            prize_count = int(data["win"]["giftNum"])

            raffle = await RedisRaffle.get(raffle_id=raffle_id)
            if not raffle:
                created_time = datetime.datetime.fromtimestamp(self._start_time)
                gift_gen_time = created_time - datetime.timedelta(seconds=180)
                gift_name = await redis_cache.get(key=f"GIFT_TYPE_{gift_type}")

                raffle = {
                    "raffle_id": raffle_id,
                    "room_id": room_id,
                    "gift_name": gift_name,
                    "gift_type": gift_type,
                    "sender_uid": None,
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

    async def d(self, *args):
        """ danmaku to qq """
        key_type, room_id, danmaku, *_ = args
        info = danmaku.get("info", {})
        msg = str(info[1])
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"
        message = (
            f"{room_id} ({datetime.datetime.fromtimestamp(self._start_time)}) ->\n\n"
            f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
        )
        logging.info(message)
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)

    async def p(self, *args):
        """ pk """

        key_type, room_id, danmaku, *_ = args
        raffle_id = danmaku["data"]["id"]
        key = f"P${room_id}${raffle_id}"
        if await redis_cache.set_if_not_exists(key, "de-duplication"):
            await self.broadcast(json.dumps({
                "raffle_type": "pk",
                "ts": int(self._start_time),
                "real_room_id": room_id,
                "raffle_id": raffle_id,
                "gift_name": "PK",
            }, ensure_ascii=False))

    async def s(self, *args):
        """ storm """

        key_type, room_id, *_ = args
        await self.broadcast(json.dumps({
            "raffle_type": "storm",
            "ts": int(self._start_time),
            "real_room_id": room_id,
            "raffle_id": None,
            "gift_name": "节奏风暴",
        }, ensure_ascii=False))

    async def a(self, *args):
        """
        anchor

        require_type = data["require_type"]
        0: 无限制; 1: 关注主播; 2: 粉丝勋章; 3大航海； 4用户等级；5主站等级
        """
        key_type, room_id, danmaku, *_ = args
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
            await self.broadcast(json.dumps({
                "raffle_type": "anchor",
                "ts": int(self._start_time),
                "real_room_id": room_id,
                "raffle_id": raffle_id,
                "gift_name": "天选时刻",
                "join_type": join_type,
                "require": f"{require_type}-{require_value}:{require_text}",
                "gift": f"{gift_num}*{gift_name or 'null'}({gift_price})",
                "award": f"{award_num}*{award_name}",
            }, ensure_ascii=False))

    async def _handle_guard(self, room_id, guard_list):
        for info in guard_list:
            raffle_id = info['id']
            key = F"G${room_id}${raffle_id}"
            if not await redis_cache.set_if_not_exists(key, "de-duplication"):
                continue

            privilege_type = info["privilege_type"]
            if privilege_type == 3:
                gift_name = "舰长"
            elif privilege_type == 2:
                gift_name = "提督"
            elif privilege_type == 1:
                gift_name = "总督"
            else:
                gift_name = f"guard_{privilege_type}"

            await self.broadcast(json.dumps({
                "raffle_type": "guard",
                "ts": int(time.time()),
                "real_room_id": room_id,
                "raffle_id": raffle_id,
                "gift_name": gift_name,
            }, ensure_ascii=False))

            created_time = datetime.datetime.fromtimestamp(self._start_time)
            expire_time = created_time + datetime.timedelta(seconds=info["time"])
            sender = info["sender"]
            create_param = {
                "gift_id": raffle_id,
                "room_id": room_id,
                "gift_name": gift_name,
                "sender_uid": sender["uid"],
                "sender_name": sender["uname"],
                "sender_face": sender["face"],
                "created_time": created_time,
                "expire_time": expire_time,
            }
            await RedisGuard.add(raffle_id=raffle_id, value=create_param)
            logging.info(f"\tGuard found: room_id: {room_id} $ {raffle_id} ({gift_name}) <- {sender['uname']}")

    async def _handle_tv(self, room_id, gift_list):
        await InLotteryLiveRooms.add(room_id=room_id)
        gift_type_to_name_map = {}

        for info in gift_list:
            raffle_id = info["raffleId"]
            key = f"T${room_id}${raffle_id}"
            if not await redis_cache.set_if_not_exists(key, "de-duplication"):
                continue

            gift_type = info["type"]
            gift_name = info.get("thank_text", "").split("赠送的", 1)[-1]
            gift_type_to_name_map[gift_type] = gift_name
            await self.broadcast(json.dumps({
                "raffle_type": "tv",
                "ts": int(self._start_time),
                "real_room_id": room_id,
                "raffle_id": raffle_id,
                "gift_name": gift_name,
                "gift_type": gift_type,
                "time_wait": info["time_wait"],
                "max_time": info["max_time"],
            }, ensure_ascii=False))

            sender_name = info["from_user"]["uname"]
            sender_face = info["from_user"]["face"]
            created_time = datetime.datetime.fromtimestamp(self._start_time)
            logging.info(f"\tLottery found: room_id: {room_id} $ {raffle_id} ({gift_name}) <- {sender_name}")

            create_param = {
                "raffle_id": raffle_id,
                "room_id": room_id,
                "gift_name": gift_name,
                "gift_type": gift_type,
                "sender_uid": None,
                "sender_name": sender_name,
                "sender_face": sender_face,
                "created_time": created_time,
                "expire_time": created_time + datetime.timedelta(seconds=info["time"])
            }
            await RedisRaffle.add(raffle_id=raffle_id, value=create_param, _pre=True)

        for gift_type, gift_name in gift_type_to_name_map.items():
            await redis_cache.set(key=f"GIFT_TYPE_{gift_type}", value=gift_name)

    async def lottery_or_guard(self, *args):
        key_type, room_id, *_ = args
        flag, result = await BiliApi.lottery_check(room_id=room_id)
        if not flag and "Empty raffle_id_list" in result:
            await asyncio.sleep(1)
            flag, result = await BiliApi.lottery_check(room_id=room_id)

        if not flag:
            logging.error(f"Cannot get lottery({key_type}) from room: {room_id}. reason: {result}")
            return

        guards, gifts = result
        await self._handle_guard(room_id, guards)
        await self._handle_tv(room_id, gifts)


async def receive_prize_from_udp_server(task_q: asyncio.Queue, broadcast_target: asyncio.coroutines):
    await mq_source_to_raffle.start_listen()

    while True:
        start_time = time.time()

        sources = []
        try:
            while True:
                sources.append(mq_source_to_raffle.get_nowait())
        except asyncio.queues.QueueEmpty:
            pass

        de_dup = set()

        for msg in sources:
            key_type, room_id, *_ = msg
            if key_type in ("R", "D", "P", "S", "A"):
                executor = Executor(start_time=start_time, br=broadcast_target)
                task_q.put_nowait(getattr(executor, key_type.lower())(*msg))
                # logging.info(f"Assign task: {key_type} room_id: {room_id}")

            elif key_type in ("G", "T", "Z"):
                if room_id not in de_dup:
                    de_dup.add(room_id)
                    executor = Executor(start_time=start_time, br=broadcast_target)
                    task_q.put_nowait(executor.lottery_or_guard(*msg))
                    logging.info(f"Assign task: {key_type} room_id: {room_id}")

        cost = time.time() - start_time
        if cost < 1:
            await asyncio.sleep(1 - cost)


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
        for ws in set(app['ws']):
            await ws.send_str(f"{message}\n")

    task_q = asyncio.Queue()
    receiver_task = asyncio.create_task(receive_prize_from_udp_server(task_q, broadcast_target))

    async def worker(index):
        while True:
            c = await task_q.get()
            start_time = time.time()
            try:
                await c
            except Exception as e:
                logging.error(f"RAFFLE worker[{index}] error: {e}\n{traceback.format_exc()}")
            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.warning(f"RAFFLE worker[{index}] exec long time: {cost_time:.3f}")

    await asyncio.gather(receiver_task, *[asyncio.create_task(worker(_)) for _ in range(8)])


loop = asyncio.get_event_loop()
loop.run_until_complete(main())



2019-12-30 20:23:22,710 [INFO]: DANMU_MSG: put to mq, room_id: 5643058, msg: {'cmd': 'DANMU_MSG', 'info': [[0, 1, 25, 16750592, 1577708602530, 0, 0, '81a1fba3', 0, 2, 0], '哔哩哔哩 (?-?)つロ 干杯~', [64782616, '温柔祯', 0, 0, 0, 10000, 1, ''], [19, '小孩梓', '阿梓从小就很可爱', 80397, 16752445, '', 0], [35, 0, 10512625, '>50000'], ['title-278-1', 'title-278-1'], 0, 0, None, {'ts': 1577708602, 'ct': '18B0685D'}, None, None]}
2019-12-30 20:23:23,243 [INFO]: ('5643058 (2019-12-30 20:23:23.243097) ->\n\n', '[小孩梓 19] [64782616][温柔祯][35]-> 哔哩哔哩 (?-?)つロ 干杯~')
2019-12-30 20:23:31,013 [INFO]: SOURCE: ANCHOR_LOT_AWARD, room_id: 21432674, msg:
2019-12-30 20:23:36,012 [INFO]: SOURCE: ANCHOR_LOT_AWARD, room_id: 21677811, msg:
2019-12-30 20:23:47,574 [INFO]: SOURCE: ANCHOR_LOT_START, room_id: 21432674, 关注主播 -> 1元红包
2019-12-30 20:23:49,105 [INFO]: SOURCE: SEND_GIFT-节奏风暴, room_