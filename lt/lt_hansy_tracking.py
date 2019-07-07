import asyncio
import traceback
from config.log4 import lt_raffle_id_getter_logger as logging
from utils.dao import DanmakuMessageQ, redis_cache
from cqhttp import CQHttp
from config import CQBOT
bot = CQHttp(**CQBOT)


class Executor(object):
    async def run(self):
        while True:
            msg = await DanmakuMessageQ.get("DANMU_MSG", timeout=50)
            if msg is None:
                continue

            message, created_time, msg_from_room_id, *_ = msg
            if msg_from_room_id == 2516117:
                return

            info = message["info"]
            uid = info[2][0]
            msg = str(info[1])
            user_name = info[2][1]
            is_admin = info[2][2]
            ul = info[4][0]
            d = info[3]
            dl = d[0] if d else "-"
            deco = d[1] if d else "undefined"

            qq_msg = f"{msg_from_room_id}: {'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
            logging.info(qq_msg)
            bot.send_private_msg(user_id=80873436, message=qq_msg)


async def main():
    logging.info("Starting Hansy tracking process...")

    try:
        executor = Executor()
        await executor.run()
    except Exception as e:
        logging.error(f"Hansy tracking process shutdown! e: {e}, {traceback.format_exc()}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
