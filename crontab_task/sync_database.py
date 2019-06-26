import time
import json
import logging
import asyncio
import aioredis

from config.log4 import crontab_task_logger as logging
from config import REDIS_CONFIG
from utils.model import User, GiftRec, LiveRoomInfo, objects
from utils.dao import ValuableLiveRoom

loop = asyncio.get_event_loop()


class SyncTool(object):
    @classmethod
    async def get_or_update_user_obj(cls, uid, name, face):
        if uid is None:
            users = await objects.execute(User.select().where(User.name == name))
            if users:
                return users[0]
            else:
                return await objects.create(User, name=name, uid=uid, face=face)

        users = await objects.execute(User.select().where(User.uid == uid))
        if users:
            user_obj = users[0]
            if user_obj.name != name:
                logging.info("User obj name update: %s -> %s" % (user_obj.name, name))
                user_obj.name = name
                await objects.update(user_obj)
            return user_obj
        else:
            users = await objects.execute(User.select().where(User.name == name))
            if users:
                user_obj = users[0]
                user_obj.uid = uid
                logging.info("User obj(%s) uid update: %s -> %s" % (name, user_obj.uid, uid))
                await objects.update(user_obj)
                return user_obj
            else:
                return await objects.create(User, name=name, uid=uid, face=face)

    @classmethod
    async def proc_single_info(cls, k, data):
        try:
            r = json.loads(data.decode("utf-8"))
        except Exception as e:
            logging.error("Error in sync_tv_single_rec: %s" % e)
            return

        uid = r.get("uid", None)
        name = r["name"]
        face = r["face"]
        user_obj = await cls.get_or_update_user_obj(uid=uid, name=name, face=face)
        if uid is None:
            logging.error("User name is None! key: %s, name: %s, user_obj.uid: %s" % (k, r["name"], user_obj.uid))

        create_param = {
            "key": k,
            "room_id": r["room_id"],
            "gift_id": r["gift_id"],
            "gift_name": r["gift_name"],
            "gift_type": r["gift_type"],
            "sender": user_obj,
            "sender_type": r["sender_type"],
            "created_time": r["created_time"],
            "status": r["status"],
        }
        return create_param

    @classmethod
    async def sync_rec(cls, redis):
        keys = await redis.execute("keys", "NG*") + await redis.execute("keys", "_T*")
        keys = {_.decode("utf-8") for _ in keys}
        db_keys = await objects.execute(GiftRec.select(GiftRec.key).where(GiftRec.key << keys))
        need_synced_keys = keys - {_.key for _ in db_keys}
        logging.info("Need sync count: %s." % len(need_synced_keys))

        source_info = {}
        count = 0
        for k in need_synced_keys:
            count += 1
            r = await redis.execute("get", k)
            source_info[k] = r
            if count > 0 and count % 100 == 0:
                logging.info("%s redis key proceed." % count)

        need_create_gift_rec = []
        for k, info in source_info.items():
            param = await cls.proc_single_info(k, info)
            if param is not None:
                need_create_gift_rec.append(param)

            if len(need_create_gift_rec) >= 100:
                r = await objects.execute(GiftRec.insert_many(need_create_gift_rec))
                logging.info("Bulk create succeed! r: %s" % r)
                need_create_gift_rec = []

        if need_create_gift_rec:
            r = await objects.execute(GiftRec.insert_many(need_create_gift_rec))
            logging.info("Bulk create succeed! r: %s" % r)

    @classmethod
    async def sync_valuable_live_room(cls):
        condition = (
            (LiveRoomInfo.guard_count > 5)
            & (
                (LiveRoomInfo.guard_count > 30)
                | (LiveRoomInfo.real_room_id != LiveRoomInfo.short_room_id)
                | (LiveRoomInfo.attention > 10000)
            )
        )
        select = (LiveRoomInfo.real_room_id, LiveRoomInfo.guard_count, LiveRoomInfo.attention)
        order_by = (LiveRoomInfo.guard_count.desc(), LiveRoomInfo.attention.desc())
        query = LiveRoomInfo.select(*select).where(condition).distinct().order_by(*order_by)
        r = await objects.execute(query)
        room_id = {e.real_room_id for e in r}
        logging.info(F"Valuable live rooms get from db success, count: {len(room_id)}")

        existed = set(await ValuableLiveRoom.get_all())
        need_add = room_id - existed
        need_del = existed - room_id

        r = await ValuableLiveRoom.add(*need_add)
        r2 = await ValuableLiveRoom.delete(*need_del)
        logging.info(f"Save to redis result: add: {r}, del: {r2}")

    @classmethod
    async def run(cls):
        start_time = time.time()
        await objects.connect()
        redis = await aioredis.create_connection(
            address='redis://%s:%s' % (REDIS_CONFIG["host"], REDIS_CONFIG["port"]),
            db=REDIS_CONFIG["db"],
            password=REDIS_CONFIG["password"],
            loop=loop
        )

        await cls.sync_rec(redis)
        await cls.sync_valuable_live_room()

        redis.close()
        await redis.wait_closed()
        await objects.close()
        logging.info("Execute finished, cost: %s.\n\n" % (time.time() - start_time))


loop.run_until_complete(SyncTool.run())
