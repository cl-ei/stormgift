import random
import datetime
from aiohttp import web
from utils.dao import redis_cache
from config.log4 import website_logger as logging
from config.g import QQ_NUMBER_DD
from utils.cq import async_zy


async def sms(request):
    r = await request.text()
    r = r.strip()
    logging.info(f"Receive sms: [{r}]")
    key = "CL_SMS"

    new_message_id = []
    for l in r.split("\n"):
        try:
            m_id, sender, st, text, *_ = l.split("$")
            if m_id == "null":
                m_id = f"s{random.randint(0x100000000000, 0xFFFFFFFFFFFF):0x}"
            else:
                m_id = int(m_id.strip())

            if not await redis_cache.set_is_member(key, m_id):
                new_message_id.append(m_id)
                message = f"{sender} [{m_id}]@{datetime.datetime.fromtimestamp(int(st)/1000)} ->\n\n{text}"
                await async_zy.send_private_msg(user_id=QQ_NUMBER_DD, message=message)

        except Exception as e:
            logging.error(f"E: {e}")

    await redis_cache.set_add(key, *new_message_id)
    return web.Response(text=f"OK")
