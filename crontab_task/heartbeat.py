import asyncio
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator
from config.log4 import crontab_task_logger as logging


async def post_heartbeat(index, total, lt_user_obj):
    cookie = lt_user_obj.cookie
    r, data = await BiliApi.post_heartbeat_5m(cookie)
    if not r:
        logging.error(f"Post heartbeat failed! msg: {data}")
        return

    r, data = await BiliApi.post_heartbeat_last_timest(cookie)
    if not r:
        logging.error(f"Cannot post last time st! msg: {data}")
        return

    r, data = await BiliApi.post_heartbeat_app(cookie=cookie, access_token=lt_user_obj.access_token)
    if not r:
        logging.error(f"Cannot post last time st! msg: {data}")
        return
    logging.info(f"({index + 1}/{total}) Post heartbeat for {lt_user_obj.name}(uid: {lt_user_obj.DedeUserID}) done.")


async def main():
    objs = await DBCookieOperator.get_objs(available=True, is_vip=True)
    for i, obj in enumerate(objs):
        await post_heartbeat(i, len(objs), obj)
        await asyncio.sleep(5)
    logging.info(f"Post heart beat task done({len(objs)}).\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
