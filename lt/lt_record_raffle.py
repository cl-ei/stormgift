import time
import json
import asyncio
import datetime
import traceback
from random import random
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import lt_raffle_id_getter_logger as logging
from utils.dao import DanmakuMessageQ, redis_cache
from utils.reconstruction_model import objects, Raffle

from config import config
from utils.cq import CQClient
from utils.dao import RaffleToCQPushList


api_root = config["ml_bot"]["api_root"]
access_token = config["ml_bot"]["access_token"]
ml_qq = CQClient(api_root=api_root, access_token=access_token)


GIFT_TYPE_TO_NAME = {
    "small_tv": "小电视飞船抽奖",
    "GIFT_30035": "任意门抽奖",
    "GIFT_30207": "幻乐之声抽奖",
    "GIFT_20003": "摩天大楼抽奖",
}


class Executor(object):
    async def record_raffle_info(self, msg):
        danmaku, created_time, msg_from_room_id, *_ = msg
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

            raffle_obj = await Raffle.get_by_id(raffle_id)
            if not raffle_obj:
                sender_uid = await ReqFreLimitApi.get_uid_by_name(sender_name)
                gift_gen_time = created_time - datetime.timedelta(seconds=180)
                gift_name = GIFT_TYPE_TO_NAME.get(gift_type, "-")
                raffle_create_param = {
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
                raffle_obj = await Raffle.record_raffle_before_result(**raffle_create_param)

            update_param = {
                "prize_gift_name": prize_gift_name,
                "prize_count": prize_count,
                "winner_uid": winner_uid,
                "winner_name": winner_name,
                "winner_face": winner_face,
                "danmaku_json_str": json.dumps(danmaku),
            }
            await Raffle.update_raffle_result(raffle_obj, **update_param)
            log_msg = f"Raffle saved! cmd: {cmd}, save result: id: {raffle_obj.id}. "

            qq = await RaffleToCQPushList.get(bili_uid=winner_uid)
            if qq:
                message = f"恭喜{winner_name}[{winner_uid}]中了{prize_gift_name}！\n[CQ:at,qq={qq}]"
                r = await ml_qq.send_group_msg(group_id=981983464, message=message)
                log_msg += f"__ML NOTICE__ r: {r}"

            logging.info(log_msg)

        else:
            return f"RAFFLE_RECORD received error cmd `{danmaku['cmd']}`!"

    async def run(self):
        monitor_commands = ['RAFFLE_END', 'TV_END']

        current_proc_message_key = "LT_RECORD_RAFFLE_CURRENT_PROC_MSG"
        msg = await redis_cache.get(current_proc_message_key)
        if msg is not None:
            logging.warn(f"Found UNFINISHED TASK, put back to mq: {msg}")
            await DanmakuMessageQ.put(msg)
            await redis_cache.delete(current_proc_message_key)

        while True:
            msg = await DanmakuMessageQ.get(*monitor_commands, timeout=50)
            if msg is None:
                continue

            # 保存当前处理的任务
            await redis_cache.set(current_proc_message_key, msg)

            start_time = time.time()
            task_id = str(random())[2:]
            logging.info(f"RAFFLE_RECORD Task[{task_id}] start...")

            try:
                # 此操作必须是可重入的！
                r = await self.record_raffle_info(msg)
            except Exception as e:
                logging.error(f"RAFFLE_RECORD Task[{task_id}] error: {e}, msg: `{msg}`, {traceback.format_exc()}")
            else:

                # 确认当前处理任务已完成
                await redis_cache.delete(current_proc_message_key)

                cost_time = time.time() - start_time
                logging.info(f"RAFFLE_RECORD Task[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.info("Starting Raffle record process...")

    await objects.connect()

    try:
        executor = Executor()
        await executor.run()
    except Exception as e:
        logging.error(f"Raffle record process shutdown! e: {e}, {traceback.format_exc()}")
    finally:
        await objects.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
