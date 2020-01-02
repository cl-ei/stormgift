import re
import logging
import asyncio
import datetime
from utils.cq import async_zy
from utils.dao import redis_cache
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, BiliApi
from config.log4 import dxj_dd_logger as logging
from utils.highlevel_api import ReqFreLimitApi, DBCookieOperator


MONITOR_ROOM_ID = 13369254


class SignRecord:

    def __init__(self, room_id):
        self.key_root = F"LT_SIGN_{room_id}"

    async def sign(self, user_id):
        """

        :param user_id:
        :return: sign success. continue, total, rank
        """
        ukey = f"{self.key_root}_{user_id}"
        offset = 0
        today_str = str(datetime.datetime.now().date() + datetime.timedelta(days=offset))
        yesterday = str(datetime.datetime.now().date() - datetime.timedelta(days=1) + datetime.timedelta(days=offset))

        continue_key = f"{ukey}_c"
        total_key = f"{ukey}_t"

        user_today = f"{ukey}_{today_str}"
        sign_success = await redis_cache.set_if_not_exists(key=user_today, value=1, timeout=3600*36)
        continue_days = None
        total_days = None

        if sign_success:

            today_sign_key = f"{self.key_root}_{today_str}_sign_count"
            today_sign_count = await redis_cache.incr(key=today_sign_key)
            await redis_cache.expire(key=today_sign_key, timeout=3600*24)
            dec_score = 0.001*int(today_sign_count)

            user_yesterday = f"{self.key_root}_{user_id}_{yesterday}"

            if not await redis_cache.get(user_yesterday):
                await redis_cache.delete(continue_key)

            continue_days = await redis_cache.incr(continue_key)
            total_days = await redis_cache.incr(total_key)

            incr_score = 50 + min(84, 12 * (continue_days - 1)) - dec_score
            await redis_cache.sorted_set_zincr(key=self.key_root, member=user_id, increment=incr_score)

        if continue_days is None:
            continue_days = int(await redis_cache.get(continue_key))
        if total_days is None:
            total_days = int(await redis_cache.get(total_key))

        rank = await redis_cache.sorted_set_zrank(key=self.key_root, member=user_id)
        return bool(sign_success), continue_days, total_days, rank + 1

    async def get_info(self):
        return await redis_cache.sorted_set_zrange_by_score(key=self.key_root, with_scores=True)

    async def get_score(self, user_id):
        score = await redis_cache.sorted_set_zscore(key=self.key_root, member=user_id)
        try:
            return float(score)
        except (TypeError, ValueError):
            return 0


async def send_danmaku(msg, user=""):
    user = user or "LP"
    c = await DBCookieOperator.get_by_uid(user_id=user)
    if not c:
        logging.error(f"Cannot get cookie for user: {user}.")
        return

    while True:
        send_m = msg[:30]
        for _ in range(3):
            flag, data = await BiliApi.send_danmaku(message=send_m, room_id=MONITOR_ROOM_ID, cookie=c.cookie)
            if flag:
                if data == "fire":
                    return

                logging.info(f"DMK success: {send_m}, reason: {data}")
                break
            else:
                logging.error(f"Dmk send failed, msg: {send_m}, reason: {data}")
                await asyncio.sleep(0.4)
        else:
            logging.error(f"Cannot send danmaku {send_m}. now return.")
            return

        msg = msg[30:]
        if msg:
            await asyncio.sleep(1.1)
        else:
            return


s = SignRecord(room_id=MONITOR_ROOM_ID)


async def proc_message(message):
    cmd = message.get("cmd", "")
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
            return await send_danmaku(msg)

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
            await send_danmaku(danmaku)

        elif msg == "船员":
            result = await ReqFreLimitApi.get_guard_count()
            r = "、".join([f"{v}个{k}" for k, v in result["gift_list"].items()])
            danmaku = f"今日统计到{r}, 共{result['total']}个"
            await send_danmaku(danmaku)

        elif msg in ("签到", "打卡"):
            sign, conti, total, rank = await s.sign(user_id=uid)

            prompt = f"{msg}成功！" if sign else f"已{msg}，"
            message = f"{user_name}{prompt}连续{msg}{conti}天、累计{total}天，排名第{rank}."
            await send_danmaku(msg=message)

        elif msg == "积分":
            score = await s.get_score(user_id=uid)
            message = f"{user_name}现在拥有{score:.2f}积分."
            await send_danmaku(msg=message)

        else:
            for key_word in ("大气大气~", "现在拥有", "连续打卡", "连续签到", "."):
                if key_word in msg:
                    return
            if re.match(r"\S*第?\d\.$", msg):
                return

            await async_zy.send_private_msg(user_id=80873436, message=f"自己的直播间: \n\n{msg_record}")


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
