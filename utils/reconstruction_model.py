import peewee
import asyncio
import datetime
import traceback
from random import randint
from peewee_async import Manager, PooledMySQLDatabase
from config import MYSQL_CONFIG
from config.log4 import model_operation_logger as logging


mysql_db = PooledMySQLDatabase(**MYSQL_CONFIG)
loop = asyncio.get_event_loop()
objects = Manager(mysql_db, loop=loop)


def random_datetime():
    return datetime.datetime.now() - datetime.timedelta(days=randint(3600, 4000))


class BiliUser(peewee.Model):
    uid = peewee.IntegerField(unique=True, null=True, index=True)
    name = peewee.CharField(index=True)
    face = peewee.CharField()
    user_info_update_time = peewee.DateTimeField(default=random_datetime)

    short_room_id = peewee.IntegerField(null=True, unique=True)
    real_room_id = peewee.IntegerField(null=True, unique=True, index=True)
    title = peewee.CharField(default="")
    create_at = peewee.CharField(default="2010-12-00 00:00:00")
    attention = peewee.IntegerField(default=0)
    guard_count = peewee.IntegerField(default=0)
    room_info_update_time = peewee.DateTimeField(index=True, default=random_datetime)

    class Meta:
        database = mysql_db

    @classmethod
    async def get_or_update(cls, uid, name, face=""):
        if uid is None:
            try:
                return await objects.get(BiliUser, name=name)

            except peewee.DoesNotExist:
                user_obj = await objects.create(
                    BiliUser,
                    name=name,
                    face=face,
                    user_info_update_time=datetime.datetime.now()
                )
                return user_obj

        try:
            user_obj = await objects.get(BiliUser, uid=uid)

            if user_obj.name != name:
                user_obj.name = name
                user_obj.face = face
                user_obj.user_info_update_time = datetime.datetime.now()
                await objects.update(user_obj, only=("name", "face", "user_info_update_time"))

            return user_obj

        except peewee.DoesNotExist:

            # 不能通过uid来获取user obj， 但name不为空， 库中可能存在user name跟此条相同的记录
            # 直接创建的话，可能会造成很多重复记录  因此找出已经存在的记录 更新之
            try:
                existed_user_obj = await objects.get(BiliUser, name=name)

                existed_user_obj.uid = uid
                existed_user_obj.face = face
                existed_user_obj.user_info_update_time = datetime.datetime.now()
                await objects.update(existed_user_obj, only=("uid", "face", "user_info_update_time"))

                return existed_user_obj

            except peewee.DoesNotExist:

                # 既不能通过uid来获取该记录，也没有存在的name，则完整创建
                user_obj = await objects.create(
                    BiliUser,
                    name=name,
                    uid=uid,
                    face=face,
                    user_info_update_time=datetime.datetime.now()
                )
                return user_obj

    @classmethod
    async def get_by_uid(cls, uid):
        objs = await objects.execute(BiliUser.select().where(BiliUser.uid == uid))
        return objs[0] if objs else None


class Guard(peewee.Model):
    id = peewee.IntegerField(primary_key=True)
    room_id = peewee.IntegerField(index=True)
    gift_name = peewee.CharField()

    sender_obj_id = peewee.IntegerField(index=True)
    # 仅为送礼时的用户名，方便查询历史用户名
    sender_name = peewee.CharField()

    created_time = peewee.DateTimeField(default=datetime.datetime.now)
    expire_time = peewee.DateTimeField(default=datetime.datetime.now, index=True)

    class Meta:
        database = mysql_db

    @classmethod
    async def create(cls, gift_id, room_id, gift_name, sender_uid, sender_name, created_time, expire_time):

        sender = await BiliUser.get_or_update(uid=sender_uid, name=sender_name)
        try:
            return await objects.create(
                Guard,
                id=gift_id,
                room_id=room_id,
                gift_name=gift_name,
                sender_obj_id=sender.id,
                sender_name=sender_name,
                created_time=created_time,
                expire_time=expire_time,
            )
        except peewee.IntegrityError as e:
            error_msg = f"{e}"
            if "Duplicate entry" in error_msg:
                old_rec = await objects.get(Guard, id=gift_id)
                old_rec.room_id = room_id
                old_rec.gift_name = gift_name
                old_rec.sender_obj_id = sender.id
                old_rec.sender_name = sender_name
                old_rec.created_time = created_time
                old_rec.expire_time = expire_time

                await objects.update(old_rec)
                logging.warning(
                    f"Guard Duplicate entry -> id: {gift_id}, E is ignored and do force update guard record."
                )
                return old_rec
            logging.error(f"Error happened when create guard rec: {e}, {traceback.format_exc()}")
            return None


class Raffle(peewee.Model):
    id = peewee.IntegerField(primary_key=True)
    room_id = peewee.IntegerField(index=True)
    gift_name = peewee.CharField(null=True)
    gift_type = peewee.CharField(null=True)

    sender_obj_id = peewee.IntegerField(index=True)
    sender_name = peewee.CharField(null=True)
    winner_obj_id = peewee.IntegerField(null=True, index=True)
    winner_name = peewee.CharField(null=True)

    prize_gift_name = peewee.CharField(null=True)
    prize_count = peewee.IntegerField(null=True)

    created_time = peewee.DateTimeField(default=random_datetime, index=True)
    expire_time = peewee.DateTimeField(default=random_datetime, index=True)

    raffle_result_danmaku = peewee.CharField(null=True, max_length=20480)

    class Meta:
        database = mysql_db

    @classmethod
    async def record_raffle_before_result(
        cls, raffle_id, room_id, gift_name, gift_type, sender_uid, sender_name, sender_face, created_time, expire_time,
    ):
        sender = await BiliUser.get_or_update(uid=sender_uid, name=sender_name, face=sender_face)
        try:
            return await objects.create(
                cls,
                id=raffle_id,
                room_id=room_id,
                gift_name=gift_name,
                gift_type=gift_type,
                sender_obj_id=sender.id,
                sender_name=sender_name,
                created_time=created_time,
                expire_time=expire_time,
            )
        except peewee.IntegrityError as e:
            error_msg = f"{e}"
            if "Duplicate entry" in error_msg:
                old_rec = await objects.get(Raffle, id=raffle_id)
                old_rec.room_id = room_id
                old_rec.gift_name = gift_name
                old_rec.gift_type = gift_type
                old_rec.sender_obj_id = sender.id
                old_rec.sender_name = sender_name
                old_rec.created_time = created_time
                old_rec.expire_time = expire_time

                await objects.update(old_rec)
                logging.warning(
                    f"Raffle Duplicate entry -> id: {raffle_id}, E is ignored and do force update guard record."
                )
                return old_rec
            logging.error(f"Raffle Error happened when create raffle rec: {e}, {traceback.format_exc()}")
            return None

    @classmethod
    async def update_raffle_result(
        cls,
        raffle_id, room_id,
        prize_gift_name, prize_count,
        winner_uid, winner_name, winner_face,
        expire_time, danmaku_json_str=""
    ):
        sender = await BiliUser.get_or_update(uid=winner_uid, name=winner_name, face=winner_face)
        try:
            raffle_obj = await objects.get(Raffle, id=raffle_id)

            raffle_obj.prize_gift_name = prize_gift_name
            raffle_obj.prize_count = prize_count
            raffle_obj.winner_obj_id = sender.id
            raffle_obj.winner_name = winner_name
            raffle_obj.raffle_result_danmaku = danmaku_json_str

            await objects.update(
                obj=raffle_obj,
                only=("prize_gift_name", "prize_count", "winner_obj_id", "winner_name", "raffle_result_danmaku")
            )

            return raffle_obj

        except peewee.DoesNotExist:
            return None
