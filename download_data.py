import os
import time
import logging
import asyncio
import aiomysql
import datetime
import configparser
from utils.db_raw_query import AsyncMySQL
from config.log4 import lt_db_sync_logger as logging
from utils.reconstruction_model import Guard, Raffle, BiliUser, objects


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
        await cls.sync(table_name="guard")

        cost = time.time() - start_time
        logging.info(f"Execute finished, cost: {cost/60:.3f} min.\n\n")


async def sync_guard():
    records = await XNodeMySql.execute("select id from guard;")
    existed_records = await AsyncMySQL.execute("select id from guard;")
    existed_ids = {row[0] for row in existed_records}
    new_id_list = sorted([r[0] for r in records if r[0] not in existed_ids])
    print(f"Need Sync {len(new_id_list)}")
    if len(new_id_list) == 0:
        print(F"Guard done!")
        return True

    this_time = new_id_list[:10000]
    records = await XNodeMySql.execute("select * from guard where id in %s;", (this_time, ))
    user_objs_ids = [row[3] for row in records]
    users = await XNodeMySql.execute(f"select id, uid, name, face from biliuser where id in %s;", (user_objs_ids, ))
    user_dict = {row[0]: (row[1], row[2], row[3]) for row in users}

    for i, r in enumerate(records):
        user_obj_id = r[3]
        sender_uid, sender_name, sender_face = user_dict[user_obj_id]
        guard_obj = await Guard.create(
            gift_id=r[0],
            room_id=r[1],
            gift_name=r[2],
            sender_uid=sender_uid,
            sender_name=sender_name,
            sender_face=sender_face,
            created_time=r[5],
            expire_time=r[6],
        )
        if i % 1000 == 0:
            logging.info(f"{i} guard_obj created: {guard_obj.id}, {guard_obj.sender_name}")


async def sync_raffle():
    records = await XNodeMySql.execute("select id from raffle;")
    existed_ids = await AsyncMySQL.execute("select distinct id from raffle;")
    existed_ids = {row[0] for row in existed_ids}
    need_sync = [r[0] for r in records if r[0] not in existed_ids]
    print(f"Raffle need sync: {len(need_sync)}")
    if len(need_sync) == 0:
        return True

    id_list = need_sync[:10000]
    records = await XNodeMySql.execute(
        (
            f"select * from raffle "
            f"where id in %s and winner_obj_id is not null "
            f"order by id asc limit 100000"
        ),
        (id_list, )
    )
    sender_obj_ids = [row[4] for row in records]
    winner_obj_ids = [row[6] for row in records]

    user_objs_ids = set(sender_obj_ids + winner_obj_ids)
    users = await XNodeMySql.execute(f"select id, uid, name, face from biliuser where id in %s;", (user_objs_ids, ))
    user_dict = {row[0]: (row[1], row[2], row[3]) for row in users}

    for i, r in enumerate(records):
        sender_obj_id = r[4]
        winner_obj_id = r[6]

        if sender_obj_id not in user_dict or winner_obj_id not in user_dict:
            continue

        sender_uid, sender_name, sender_face = user_dict[sender_obj_id]
        winner_uid, winner_name, winner_face = user_dict[winner_obj_id]
        raffle_obj = await Raffle.create(
            raffle_id=r[0],
            room_id=r[1],
            gift_name=r[2],
            gift_type=r[3],
            sender_uid=sender_uid,
            sender_name=sender_name,
            sender_face=sender_face,
            created_time=r[10],
            expire_time=r[11],
            prize_gift_name=r[8],
            prize_count=r[9],
            winner_uid=winner_uid,
            winner_name=winner_name,
            winner_face=winner_face,
        )
        if i % 1000 == 0:
            logging.info(f"{i} raffle_obj created: {raffle_obj.id}, {raffle_obj.sender_name}")


async def sync_user():
    all_user_obj_ids = set()
    records = await XNodeMySql.execute("select sender_obj_id, winner_obj_id from raffle;")
    for r in records:
        all_user_obj_ids.add(r[0])
        all_user_obj_ids.add(r[1])
    records = await XNodeMySql.execute("select sender_obj_id from raffle;")
    all_user_obj_ids |= {r[0] for r in records}
    all_user_obj_ids = sorted(all_user_obj_ids)

    offset = 0
    limit = 5000
    while offset < len(all_user_obj_ids):
        users = all_user_obj_ids[offset: offset+limit]
        offset += limit

        users = await XNodeMySql.execute(
            f"select id, uid, name, face "
            f"from biliuser "
            f"where id in %s and uid is not null;",
            (users, )
        )
        existed_user = await AsyncMySQL.execute(f"select distinct uid from biliuser where uid is not NULL;")
        existed_user = {r[0] for r in existed_user}
        create_args = []
        for row in users:
            id_, uid, name, face = row
            if uid not in existed_user:
                create_args.append((uid, name, face))

        if create_args:
            r = await objects.execute(BiliUser.insert_many(create_args, ["uid", "name", "face"]))
            print(f"insert_many: {r}")


async def main():
    await objects.connect()
    await sync_user()

    return
    r1 = await sync_raffle()
    r2 = await sync_guard()
    if r1 is True and r2 is True:
        logging.info("ALL Done!")
        while True:
            await asyncio.sleep(100)


loop.run_until_complete(main())
