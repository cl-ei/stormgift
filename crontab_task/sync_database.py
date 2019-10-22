import time
import logging
import asyncio
import datetime
from utils.biliapi import BiliApi
from utils.db_raw_query import AsyncMySQL
from utils.highlevel_api import ReqFreLimitApi
from utils.dao import ValuableLiveRoom, redis_cache
from config.log4 import lt_db_sync_logger as logging
from utils.reconstruction_model import objects, BiliUser, Raffle, Guard

loop = asyncio.get_event_loop()


class SyncTool(object):

    @classmethod
    async def sync_valuable_live_room(cls):
        query = await AsyncMySQL.execute(
            "select real_room_id from biliuser "
            "where guard_count > 0 or attention > 10000 or real_room_id != short_room_id "
            "order by guard_count desc, attention desc ;"
        )
        room_id = {row[0] for row in query}

        logging.info(F"Valuable live rooms get from db success, count: {len(room_id)}")
        existed = set(await ValuableLiveRoom.get_all())
        need_add = room_id - existed
        need_del = existed - room_id

        r = await ValuableLiveRoom.add(*need_add)
        r2 = await ValuableLiveRoom.delete(*need_del)
        logging.info(f"Save to redis result: add: {r}, del: {r2}")

    @staticmethod
    async def fix_user_record_missed_uid():
        non_uid_users = await objects.execute(BiliUser.select().where(BiliUser.uid == None))
        logging.info(f"non_uid_users count: {len(non_uid_users)}")

        for non_uid_user_obj in non_uid_users:
            lastest_user_name = non_uid_user_obj.name
            fix_failed_key = f"FIX_MISSED_USER_{lastest_user_name}"
            if await redis_cache.get(fix_failed_key):
                logging.info(f"Found failed key: {fix_failed_key}, now skip.")
                continue

            uid = await ReqFreLimitApi.get_uid_by_name(lastest_user_name)
            if not uid:
                await redis_cache.set(fix_failed_key, "f", 3600*72)
                logging.warning(f"Cannot get uid by name: `{non_uid_user_obj.name}`")
                continue

            has_uid_user_objs = await objects.execute(
                BiliUser.select().where(BiliUser.uid == uid)
            )
            if has_uid_user_objs:
                has_uid_user_obj = has_uid_user_objs[0]
                logging.info(
                    f"User uid: {uid} -> name: {lastest_user_name} duplicated! "
                )

                # 有两个user_obj
                # 1.先把旧的existed_user_obj的name更新
                has_uid_user_obj.name = lastest_user_name
                await objects.update(has_uid_user_obj, only=("name",))

                # 2.迁移所有的raffle记录
                updated_count = 0
                for raffle_obj in await objects.execute(
                        Raffle.select().where(Raffle.sender_obj_id == non_uid_user_obj.id)
                ):
                    updated_count += 1
                    raffle_obj.sender_obj_id = has_uid_user_obj.id
                    await objects.update(raffle_obj, only=("sender_obj_id",))

                for raffle_obj in await objects.execute(
                        Raffle.select().where(Raffle.winner_obj_id == non_uid_user_obj.id)
                ):
                    updated_count += 1
                    raffle_obj.winner_obj_id = has_uid_user_obj.id
                    await objects.update(raffle_obj, only=("winner_obj_id",))

                # 3 迁移guard记录
                for guard_obj in await objects.execute(
                        Guard.select().where(Guard.sender_obj_id == non_uid_user_obj.id)
                ):
                    updated_count += 1
                    guard_obj.sender_obj_id = has_uid_user_obj.id
                    await objects.update(guard_obj, only=("sender_obj_id",))

                # 4.删除空的user_obj
                await objects.delete(non_uid_user_obj)

                logging.info(f"User obj updated! raffle update count: {updated_count}")

            else:
                non_uid_user_obj.uid = uid
                await objects.update(non_uid_user_obj, only=("uid",))
                logging.info(f"User obj updated! {lastest_user_name} -> {uid}, obj id: {non_uid_user_obj.id}")

    @classmethod
    async def search_short_number(cls):
        logging.info("Get room id list from db...")
        query = await AsyncMySQL.execute(
            (
                "select distinct room_id, count(id) "
                "from raffle "
                "where room_id not in (select real_room_id from biliuser where room_info_update_time >= %s) "
                "group by room_id order by 2 desc;"
            ), (datetime.datetime.now() - datetime.timedelta(days=2))
        )
        room_id_list = [row[0] for row in query]

        query = await AsyncMySQL.execute(
            (
                "select distinct room_id, count(id) "
                "from guard "
                "where room_id not in (select real_room_id from biliuser where room_info_update_time >= %s) "
                "group by room_id order by 2 desc;"
            ), (datetime.datetime.now() - datetime.timedelta(days=2))
        )
        room_id_list2 = [row[0] for row in query]

        finnal_list = []
        while True:
            if not room_id_list:
                break
            else:
                finnal_list.append(room_id_list.pop())

            if not room_id_list2:
                break
            else:
                finnal_list.append(room_id_list2.pop())
        finnal_list.extend(room_id_list + room_id_list2)
        search_list = []
        for room_id in finnal_list:
            if room_id not in search_list:
                search_list.append(room_id)

        logging.info(f"Start searching, total count: {len(search_list)}")
        for room_id in search_list:
            req_url = "https://api.live.bilibili.com/AppRoom/index?platform=android"
            flag, response = await BiliApi.get(req_url, timeout=10, data={"room_id": room_id}, check_error_code=True)
            if flag and response["code"] in (0, "0"):

                data = response["data"]
                uid = data["mid"]
                name = data["uname"]
                face = data["face"]
                user_info_update_time = datetime.datetime.now()
                short_room_id = data["show_room_id"]
                real_room_id = data["room_id"]
                title = data["title"]
                create_at = data["create_at"]
                attention = data["attention"]

                req_url = f"https://api.live.bilibili.com/guard/topList?page=1"
                flag, guard_response = await BiliApi.get(
                    req_url,
                    data={"roomid": real_room_id, "ruid": uid},
                    timeout=10,
                    check_error_code=True
                )
                if not flag:
                    logging.error(f"Error! e: {guard_response}")
                    continue
                guard_count = guard_response["data"]["info"]["num"]
                room_info_update_time = datetime.datetime.now()

                obj = await BiliUser.full_create_or_update(
                    uid=uid,
                    name=name,
                    face=face,
                    user_info_update_time=user_info_update_time,
                    short_room_id=short_room_id,
                    real_room_id=real_room_id,
                    title=title,
                    create_at=create_at,
                    attention=attention,
                    guard_count=guard_count,
                    room_info_update_time=room_info_update_time,
                )

                logging.info(
                    f"Update success ! room_id: {real_room_id} -> {short_room_id}, {uid} -> {name},"
                    f" attention: {attention}, guard: {guard_count}, obj: {obj.id}"
                )

            await asyncio.sleep(5)

    @classmethod
    async def run(cls):
        start_time = time.time()

        execute_key = "LT_SYNC_DATABASE_TASK_RUNNING"
        finished = await redis_cache.set_if_not_exists(execute_key, 1, timeout=60*55)
        if not finished:
            logging.error(f"DataBase syncing! Now exit...")
            return

        await objects.connect()

        await cls.sync_valuable_live_room()
        await cls.fix_user_record_missed_uid()
        # await cls.search_short_number()

        await objects.close()
        await redis_cache.delete(execute_key)

        cost = time.time() - start_time
        logging.info(f"Execute finished, cost: {cost}.\n\n")


loop.run_until_complete(SyncTool.run())
