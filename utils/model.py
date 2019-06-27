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
