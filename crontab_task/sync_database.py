import os
import time
import logging
import asyncio
import aiomysql
import configparser
from utils.db_raw_query import AsyncMySQL
from config.log4 import lt_db_sync_logger as logging


loop = asyncio.get_event_loop()


class XNodeMySql:
    __conn = None

    @classmethod
    async def execute(cls, *args, **kwargs):
        if cls.__conn is None:
            config_file = "/etc/madliar.settings.ini"
            if not os.path.exists(config_file):
                config_file = "./madliar.settings.ini"
                print("Warning: LOCAL CONFIG FILE!")

            config = configparser.ConfigParser()
            config.read(config_file)

            c = config["xnode_mysql"]
            cls.__conn = await aiomysql.connect(
                host=c["host"],
                port=int(c["port"]),
                user=c["user"],
                password=c["password"],
                db=c["database"],
                loop=loop
            )
        cursor = await cls.__conn.cursor()
        await cursor.execute(*args, **kwargs)
        r = await cursor.fetchall()
        await cursor.close()
        # conn.close()
        return r


class SyncTool(object):

    @classmethod
    async def sync(cls, table_name="ltusercookie"):
        table_desc = await XNodeMySql.execute(f"desc {table_name};")
        table_fields = [row[0] for row in table_desc]
        id_index = table_fields.index("id")

        query = await XNodeMySql.execute(f"select * from {table_name} order by id desc;")

        for row in query:
            row_sql = ",".join(["%s" for _ in range(len(query[0]))])
            sql = f"INSERT INTO {table_name} VALUES({row_sql});"
            try:
                await AsyncMySQL.execute(sql, row, _commit=True)
            except Exception as e:
                err_msg = f"{e}"
                if "(1062," in err_msg:
                    fields = ",".join([f"{f}=%s" for f in table_fields])
                    sql = f"UPDATE {table_name} SET {fields} WHERE id={row[id_index]};"
                    await AsyncMySQL.execute(sql, row, _commit=True)
                else:
                    logging.error(err_msg)

    @classmethod
    async def run(cls):
        start_time = time.time()
        logging.info(f"Start Sync Database...")
        await cls.sync()

        cost = time.time() - start_time
        logging.info(f"Execute finished, cost: {cost/60:.3f} min.\n\n")


"""

objs = await objects.execute(BiliUser.select().where(BiliUser.real_room_id == msg_from_room_id))
if objs:
    sender = objs[0]
    sender_name = sender.name
    short_room_id = sender.short_room_id or msg_from_room_id
else:
    flag, info = await BiliApi.get_live_room_info_by_room_id(room_id=msg_from_room_id)
    if not flag:
        logging.error(f"ANCHOR_LOT_AWARD Cannot get live room info of {msg_from_room_id}, reason: {info}.")
        return

    short_room_id = info["short_id"] or msg_from_room_id
    sender_uid = info["uid"]
    flag, info = await BiliApi.get_user_info(uid=sender_uid)
    if not flag:
        logging.error(f"ANCHOR_LOT_AWARD Cannot get get_user_info. uid: {sender_uid}, reason: {info}.")
        return

    sender_name = info["name"]
    sender_face = info["face"]
    sender = await BiliUser.get_or_update(uid=sender_uid, name=sender_name, face=sender_face)
    logging.info(f"ANCHOR_LOT_AWARD Sender info get from biliapi. {sender_name}({sender_uid})")

prize_gift_name = data["award_name"]
prize_count = data["award_num"]
gift_name = "天选时刻"
gift_type = "ANCHOR"
for i, user in enumerate(data["award_users"]):
    inner_raffle_id = raffle_id + i
    winner_name = user["uname"]
    winner_uid = user["uid"]
    winner_face = user["face"]
    winner = await BiliUser.get_or_update(uid=winner_uid, name=winner_name, face=winner_face)
    create_params = {
        "id": inner_raffle_id,
        "room_id": msg_from_room_id,
        "gift_name": gift_name,
        "gift_type": gift_type,
        "winner_obj_id": winner.id,
        "winner_name": winner_name,
        "prize_gift_name": prize_gift_name,
        "prize_count": prize_count,
        "created_time": datetime.datetime.now() - datetime.timedelta(seconds=600),
        "expire_time": datetime.datetime.now()
    }
    r = await objects.create(Raffle, **create_params)
    logging.info(f"Raffle saved! cmd: {cmd}, save result: id: {r.id}. ")


from utils.dao import RaffleToCQPushList, BiliToQQBindInfo

qq_1 = await RaffleToCQPushList.get(bili_uid=winner_uid)
if qq_1:
    message = f"恭喜{winner_name}[{winner_uid}]中了{prize_gift_name}！\n[CQ:at,qq={qq_1}]"
    r = await ml_qq.send_group_msg(group_id=981983464, message=message)
    log_msg += f"__ML NOTICE__ r: {r}"

if winner_uid in (BILI_UID_DD, BILI_UID_TZ, BILI_UID_CZ):
    message = (
        f"恭喜{winner_name}({winner_uid})[CQ:at,qq={QQ_NUMBER_DD}]"
        f"获得了{sender_name}提供的{prize_gift_name}!\n"
        f"https://live.bilibili.com/{msg_from_room_id}"
    )
    await async_zy.send_private_msg(user_id=QQ_NUMBER_DD, message=message)
logging.info(log_msg)


"""

loop.run_until_complete(SyncTool.run())
