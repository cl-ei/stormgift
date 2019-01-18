import time
import json
import aioredis
import datetime
import asyncio

import peewee
from peewee_async import Manager, PooledMySQLDatabase

with open("../config/proj_config.json", "rb") as f:
    config = json.loads(f.read().decode("utf-8"))
    mysql_config = config.get("mysql")
    redis_config = config.get("redis")
mysql_db = PooledMySQLDatabase(**mysql_config)


class User(peewee.Model):
    name = peewee.CharField()
    uid = peewee.IntegerField(unique=True, null=True, )
    face = peewee.CharField()

    class Meta:
        database = mysql_db


class GiftRec(peewee.Model):
    key = peewee.CharField(unique=True)
    room_id = peewee.IntegerField()
    gift_id = peewee.IntegerField()
    gift_name = peewee.CharField()
    gift_type = peewee.CharField()
    sender = peewee.ForeignKeyField(User, related_name="gift_rec", on_delete="SET NULL", null=True)
    sender_type = peewee.IntegerField(null=True)
    created_time = peewee.DateTimeField(default=datetime.datetime.now)
    status = peewee.IntegerField()

    class Meta:
        database = mysql_db


loop = asyncio.get_event_loop()
objects = Manager(mysql_db, loop=loop)


async def get_or_update_user_obj(uid, name, face):
    _users = await objects.execute(User.select().where(User.uid == uid))
    if not _users:
        _users = await objects.execute(User.select().where(User.name == name))

    if _users:
        user_obj = list(_users)[0]
        need_update = False
        update_info = ""

        if user_obj.face != face:
            update_info += "face update: %s -> %s " % (user_obj.face, face)
            need_update = True
            user_obj.face = face

        if user_obj.name != name:
            update_info += "name update: %s -> %s " % (user_obj.name, name)
            need_update = True
            user_obj.name = name

        if need_update:
            print("User obj uid(%s) %s" % (user_obj.uid, update_info))
            await objects.update(user_obj)
    else:
        user_obj = await objects.create(User, name=name, uid=uid, face=face)
    return user_obj


async def sync_guard_single_rec(redis_conn, k):
    try:
        data = await redis_conn.execute('get', k)
        r = json.loads(data.decode("utf-8"))
    except Exception:
        return

    user_info = r["sender"]
    k = k.decode("utf-8")
    user_obj = await get_or_update_user_obj(user_info["uid"], user_info["uname"], user_info["face"])
    existed_gift_rec = await objects.execute(GiftRec.select(GiftRec.key).where(GiftRec.key == k))
    if not existed_gift_rec:
        g = await objects.create(GiftRec, **{
            "key": k,
            "room_id": int(k[2:].split("$")[0]),
            "gift_id": int(k[2:].split("$")[-1]),
            "gift_name": "guard",
            "gift_type": "G" + str(r["privilege_type"]),
            "sender": user_obj,
            "created_time": datetime.datetime.fromtimestamp(r["_saved_time"] / 1000),
            "status": r["status"],
        })
        print("\tg: %s created." % g.id)


async def sync_tv_rec():
    start_time = time.time()
    await objects.connect()

    redis_conn = await aioredis.create_connection(
        address='redis://%s:%s' % (redis_config["host"], redis_config["port"]),
        db=redis_config["db"],
        password=redis_config["auth_pass"],
        loop=loop
    )

    keys = await redis_conn.execute('keys', 'NG*')
    for k in keys:
        print("creat key: %s" % k)
        await sync_guard_single_rec(redis_conn, k)

    redis_conn.close()
    await redis_conn.wait_closed()
    await objects.close()
    print("END! cost: %s." % int(time.time() - start_time))


loop.run_until_complete(sync_tv_rec())
