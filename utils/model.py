import peewee
import asyncio
import datetime

from peewee_async import Manager, PooledMySQLDatabase
from config import MYSQL_CONFIG

mysql_db = PooledMySQLDatabase(**MYSQL_CONFIG)

loop = asyncio.get_event_loop()
objects = Manager(mysql_db, loop=loop)


class User(peewee.Model):
    name = peewee.CharField()
    uid = peewee.IntegerField(unique=True, null=True, )
    face = peewee.CharField()
    info = peewee.CharField()

    class Meta:
        database = mysql_db

    @classmethod
    async def get_or_update(cls, uid, name, face=""):
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
                user_obj.name = name
                await objects.update(user_obj)
            return user_obj
        return await objects.create(User, name=name, uid=uid, face=face)

    @classmethod
    async def get_by_uid(cls, uid):
        objs = await objects.execute(User.select().where(User.uid == uid))
        return objs[0] if objs else None


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
    expire_time = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = mysql_db

    @classmethod
    async def create(
            cls, room_id, gift_id, gift_name, gift_type,
            sender_type, created_time, status, expire_time, uid, name, face
    ):
        if gift_type in ("G1", "G2", "G3"):
            key = F"NG{room_id}${gift_id}"
        else:
            key = F"_T{room_id}${gift_id}"

        sender = await User.get_or_update(uid=uid, name=name, face=face)

        try:
            g_obj = await objects.create(
                GiftRec,
                key=key,
                room_id=room_id,
                gift_id=gift_id,
                gift_name=gift_name,
                gift_type=gift_type,
                sender=sender,
                sender_type=sender_type,
                created_time=created_time,
                status=status,
                expire_time=expire_time
            )
            return True, g_obj

        except Exception as e:
            return False, f"GiftRec.create Error: {e}"


class LiveRoomInfo(peewee.Model):
    short_room_id = peewee.IntegerField()
    real_room_id = peewee.IntegerField(null=False, unique=True)
    title = peewee.CharField()
    user_id = peewee.IntegerField()
    create_at = peewee.CharField()

    attention = peewee.IntegerField()
    guard_count = peewee.IntegerField()

    update_time = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = mysql_db

    @classmethod
    async def update_live_room(cls, short_room_id, real_room_id, title, user_id, create_at, attention, guard_count):
        try:
            live_rooms = await objects.execute(LiveRoomInfo.select().where(LiveRoomInfo.real_room_id == real_room_id))
            if live_rooms:
                live_room_obj = live_rooms[0]

                live_room_obj.short_room_id = short_room_id
                live_room_obj.real_room_id = real_room_id
                live_room_obj.title = title
                live_room_obj.user_id = user_id
                live_room_obj.create_at = create_at
                live_room_obj.attention = attention
                live_room_obj.guard_count = guard_count
                live_room_obj.update_time = datetime.datetime.now()
                await objects.update(live_room_obj)
            else:
                live_room_obj = await objects.create(
                    LiveRoomInfo,
                    short_room_id=short_room_id,
                    real_room_id=real_room_id,
                    title=title,
                    user_id=user_id,
                    create_at=create_at,
                    attention=attention,
                    guard_count=guard_count,
                    update_time=datetime.datetime.now()
                )
            return True, live_room_obj
        except Exception as e:
            import traceback
            return False, f"Error: {e}, {traceback.format_exc()}"


class MonitorWsClient(peewee.Model):
    update_time = peewee.DateTimeField(index=True)
    name = peewee.CharField()
    value = peewee.FloatField()

    class Meta:
        database = mysql_db

    @classmethod
    async def record(cls, params):
        valid_names = (
            "valuable room",
            "api room cnt",
            "active clients",
            "broken clients",
            "total clients",
            "target clients",
            "valuable hit rate",
            "msg speed",
            "msg peak speed",
            "TCP ESTABLISHED",
            "TCP TIME_WAIT",
        )
        update_time = params.get("update_time") or datetime.datetime.now()
        insert_params = []
        for key in params:
            if key in valid_names:
                insert_params.append({"update_time": update_time, "name": key, "value": params[key]})

        if insert_params:
            await objects.execute(MonitorWsClient.insert_many(insert_params))
            return True
        else:
            return False


class RaffleRec(peewee.Model):
    cmd = peewee.CharField()

    room_id = peewee.IntegerField()
    raffle_id = peewee.IntegerField(index=True)
    gift_name = peewee.CharField()
    count = peewee.IntegerField()

    msg = peewee.CharField()
    user_obj_id = peewee.IntegerField(index=True)
    created_time = peewee.DateTimeField(index=True)

    class Meta:
        database = mysql_db

    @classmethod
    async def create(cls, cmd, room_id, raffle_id, gift_name, count, msg, user_id, user_name, user_face, created_time):
        winner = await User.get_or_update(uid=user_id, name=user_name, face=user_face)
        r_obj = await objects.create(
            RaffleRec,
            cmd=cmd,
            room_id=room_id,
            raffle_id=raffle_id,
            gift_name=gift_name,
            count=count,
            msg=msg,
            user_obj_id=winner.id,
            created_time=created_time
        )
        return r_obj
