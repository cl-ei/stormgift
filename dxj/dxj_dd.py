import time
import random
import logging
import asyncio
import datetime
from cqhttp import CQHttp
from config import CQBOT
from utils.dao import redis_cache, BiliToQQBindInfo
from utils.biliapi import WsApi, BiliApi
from utils.ws import RCWebSocketClient
from utils.highlevel_api import ReqFreLimitApi, DBCookieOperator
from config.log4 import dxj_dd_logger as logging

MONITOR_ROOM_ID = 13369254
bot = CQHttp(**CQBOT)


async def send_danmaku(msg, user=""):
    user = user or "LP"
    cookie_obj = await DBCookieOperator.get_by_uid(user_id=user)
    if not cookie_obj:
        logging.error(f"Cannot get cookie for user: {user}.")
        return

    flag, msg = await BiliApi.send_danmaku(
        message=msg,
        room_id=MONITOR_ROOM_ID,
        cookie=cookie_obj.cookie
    )
    if not flag:
        logging.error(f"Danmaku [{msg}] send failed, msg: {msg}, user: {user}.")


async def proc_message(message):
    cmd = message.get("cmd")
    if cmd.startswith("DANMU_MSG"):
        info = message.get("info", {})
        msg = str(info[1])
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"
        msg_record = f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
        logging.info(msg_record)

        if msg in ("总督", "提督", "舰长", "低保"):
            await send_danmaku("|･ω･｀) 查看下方的主播简介哦")

        elif "中奖" in msg and "查询" in msg:
            if msg.startswith("#中奖查询"):
                try:
                    uid = int(msg[5:])
                except (ValueError, TypeError):
                    return

                user_name = f"uid{uid}"

            raffle_list = await ReqFreLimitApi.get_raffle_record(uid)
            if not raffle_list:
                return await send_danmaku(f"{user_name}: 七天内没有中奖纪录。")

            count = len(raffle_list)
            latest = raffle_list[0]
            interval = (datetime.datetime.now() - latest[3]).total_seconds()
            if interval < 3600:
                date_time_str = "刚刚"
            elif interval < 3600*24:
                date_time_str = f"{int(interval/3600)}小时前"
            else:
                date_time_str = f"{int(interval/(3600*24))}天前"

            msg = f"{latest[0]}在7天内中奖{count}次，最后一次{date_time_str}在{latest[1]}直播间获得{latest[2]}."
            if len(msg) <= 30:
                return await send_danmaku(msg)

            while msg:
                await send_danmaku(msg[:29])
                msg = msg[29:]
                await asyncio.sleep(1)

        elif msg.startswith("小电视"):
            int_str = msg.replace("小电视", "").strip()
            try:
                int_str = int(int_str)
            except (TypeError, ValueError):
                int_str = 0

            result = await ReqFreLimitApi.get_raffle_count(day_range=int_str)

            r = "、".join([f"{v}个{k}" for k, v in result["gift_list"].items()])
            miss = result['miss']
            miss_raffle = result['miss_raffle']
            if miss == 0 and miss_raffle == 0:
                path_prompt = "全部记录"
            elif miss > 0 and miss_raffle == 0:
                path_prompt = f"高能遗漏{miss}个"
            elif miss == 0 and miss_raffle > 0:
                path_prompt = f"高能全部记录，中奖记录漏{miss_raffle}个"
            else:
                path_prompt = f"高能漏{miss}个，中奖记录漏{miss_raffle}个"
            danmaku = (
                f"{'今日' if int_str == 0 else str(int_str) + '天前'}统计到{r}, "
                f"共{result['total']}个，{path_prompt}。"
            )

            while danmaku:
                await send_danmaku(danmaku[:30])
                danmaku = danmaku[30:]
                await asyncio.sleep(1)

        elif msg.strip() in ("船员", ):
            result = await ReqFreLimitApi.get_guard_count()
            r = "、".join([f"{v}个{k}" for k, v in result["gift_list"].items()])
            danmaku = f"今日统计到{r}, 共{result['total']}个"

            while danmaku:
                await send_danmaku(danmaku[:30])
                danmaku = danmaku[30:]
                await asyncio.sleep(0.5)

        elif msg.startswith("绑定"):
            try:
                number = int(msg[2:])
                assert 1000 <= number <= 9999
            except (ValueError, TypeError, IndexError, AssertionError):
                await send_danmaku("指令不正确。")
                return

            key = f"BILI_BIND_CHECK_KEY_{number}"
            qq = await redis_cache.get(key)
            if not qq:
                await send_danmaku("超时了。请重新绑定")

            await BiliToQQBindInfo.bind(qq=qq, bili=uid)
            await send_danmaku(f"已为你绑定到QQ：{str(qq)[:-4]}****")

        else:
            bot.send_private_msg(user_id=80873436, message=f"自己的直播间: \n\n{msg_record}")


async def main():
    async def on_connect(ws):
        logging.info("connected.")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):
        for m in WsApi.parse_msg(message):
            try:
                await proc_message(m)
            except Exception as e:
                logging.error(f"Error happened when proc_message: {e}", exc_info=True)

    new_client = RCWebSocketClient(
        url=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()

    logging.info("DD ws stated.")
    while True:
        await asyncio.sleep(1)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
