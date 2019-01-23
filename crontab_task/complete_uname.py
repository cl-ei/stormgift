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

        for user_obj in user_objs:
            uid = await cls.get_user_id(user_obj.name)
            if not uid:
                user_obj.info = "cannotupdate_%s" % uid
                await objects.update(user_obj)
                logging.info("Can not find: %s" % user_obj.name)
                continue

            existed_objs = await objects.execute(User.select().where(User.uid == uid))
            if existed_objs:
                existed_obj = existed_objs[0]
                old_name = user_obj.name
                user_obj.name = existed_obj.name
                user_obj.info = "Duplicate_%s" % existed_obj.id
                await objects.update(user_obj)
                logging.info("Duplicate! %s -> %s" % (old_name, user_obj.name))
            else:
                user_obj.uid = uid
                user_obj.info = "checked_%s" % time.time()
                await objects.update(user_obj)
                logging.info("Update uid: %s -> name: %s" % (uid, user_obj.name))

    @classmethod
    async def run(cls):
        start_time = time.time()
        await objects.connect()
        await cls.sync_rec()
        await objects.close()
        logging.info("Execute finished, cost: %s.\n\n" % (time.time() - start_time))


loop.run_until_complete(SyncTool.run())
