import time
import os
import sys
import logging
import json
import datetime
import aiohttp
import asyncio

import peewee
from peewee_async import Manager, PooledMySQLDatabase


if sys.platform == "linux":
    CONFIG_FILE = "/home/wwwroot/stormgift/config/proj_config.json"
    LOG_PATH = "/home/wwwroot/log"
else:
    CONFIG_FILE = "../config/proj_config.json"
    LOG_PATH = "../log"
fh = logging.FileHandler(os.path.join(LOG_PATH, "complete_uname.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger = logging.getLogger("complete_uname")
logger.setLevel(logging.DEBUG)
logger.addHandler(fh)
logger.addHandler(logging.StreamHandler(sys.stdout))
logging = logger


with open(CONFIG_FILE, "rb") as f:
    config = json.loads(f.read().decode("utf-8"))
    mysql_config = config.get("mysql")
mysql_db = PooledMySQLDatabase(**mysql_config)


class User(peewee.Model):
    name = peewee.CharField()
    uid = peewee.IntegerField(unique=True, null=True, )
    face = peewee.CharField()
    info = peewee.CharField()

    class Meta:
        database = mysql_db


loop = asyncio.get_event_loop()
objects = Manager(mysql_db, loop=loop)


class SyncTool(object):
    @classmethod
    async def get_or_update_user_obj(cls, uid, name, face):
        _users = None
        if uid is not None:
            _users = await objects.execute(User.select().where(User.uid == uid))
        if not _users:
            _users = await objects.execute(User.select().where(User.name == name))

        if _users:
            user_obj = list(_users)[0]
            need_update = False
            update_info = ""
            if uid is not None and user_obj.uid is None:
                update_info += "uid update: %s -> %s " % (user_obj.uid, uid)
                need_update = True
                user_obj.uid = uid

            if user_obj.face != face:
                update_info += "face update: %s -> %s " % (user_obj.face, face)
                need_update = True
                user_obj.face = face

            if user_obj.name != name:
                update_info += "name update: %s -> %s " % (user_obj.name, name)
                need_update = True
                user_obj.name = name

            if need_update:
                logging.info("User obj uid(%s) %s" % (user_obj.uid, update_info))
                await objects.update(user_obj)
        else:
            user_obj = await objects.create(User, name=name, uid=uid, face=face)
        return user_obj

    @classmethod
    async def get_user_id(cls, name):
        if not name:
            return 0

        async with aiohttp.ClientSession() as session:
            req_url = (
                "https://api.bilibili.com/x/web-interface/search/type"
                "?search_type=bili_user"
                "&highlight=1"
                "&keyword=" + name
            )
            ua = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36"
            )
            async with session.get(req_url, headers={"User-Agent": ua}) as resp:
                if resp.status != 200:
                    logging.error("Error response in get user: %s" % name)
                    return 0

                response_data = await resp.text()
                r = json.loads(response_data)
                if r.get("code") != 0:
                    logging.error("Response error, user: %s, msg: %s" % (name, r.get("message")))
                    return 0

                result_list = r.get("data", {}).get("result", []) or []
                for r in result_list:
                    if r.get("uname") == name:
                        uid = int(r.get("mid"))
                        break
                else:
                    uid = 0
                return uid

    @classmethod
    async def sync_rec(cls):
        user_objs = await objects.execute(User.select().where((User.uid == None) & (User.info == None)))
        logging.info("Need update user objs: %s" % len(user_objs))

        searched_result = {}
        for user_obj in user_objs[:100]:
            uid = await cls.get_user_id(user_obj.name)
            if uid:
                searched_result[uid] = user_obj

        existed_user_obj = await objects.execute(User.select().where(User.uid.in_(list(searched_result))))
        existed_map = {u.uid: u for u in existed_user_obj}
        for uid, user_obj in searched_result.items():
            if uid in existed_map:
                null_uid_obj = user_obj
                existed_obj = existed_map[uid]
                print("id: %s %s " % (null_uid_obj.id, existed_obj.id))
            # if existed:
            #     existed = existed[0]
            #     logging.info(
            #         "User Duplicate, rec id: %s, need updated id: %s"
            #         % (existed.id, user_obj.id)
            #     )
            #
            #     # user_obj.info = "duplicate_searched_%s_rec_%s" % (uid, existed.uid)
            #     # await objects.update(user_obj)
            # elif uid:
            #     # user_obj.uid = uid
            #     # user_obj.info = "checked_%s" % time.time()
            #     # await objects.update(user_obj)
            #     logging.info("Update uid: %s -> name: %s" % (uid, user_obj.name))

    @classmethod
    async def run(cls):
        start_time = time.time()
        await objects.connect()
        await cls.sync_rec()
        await objects.close()
        logging.info("Execute finished, cost: %s.\n\n" % (time.time() - start_time))


loop.run_until_complete(SyncTool.run())
