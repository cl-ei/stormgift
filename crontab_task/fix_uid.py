import time
import random
import logging
import asyncio
import aiomysql
import traceback
from config import MYSQL_CONFIG
from utils.dao import redis_cache
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import lt_db_sync_logger as logging


async def fix_missed_uid(execute):
    query = await execute("select name, id from biliuser where uid is null;")
    non_uid_users = {r[0]: r[1] for r in query}
    logging.info(f"non_uid_users count: {len(non_uid_users)}")

    # 过滤
    block_key_prefix = "FIX_MISSED_USER_"
    keys = [f"{block_key_prefix}{name}" for name in non_uid_users]
    result = await redis_cache.mget(*keys)
    non_blocked = {}
    blocked = []
    for i, key in enumerate(keys):
        name = key[len(block_key_prefix):]
        if result[i]:
            blocked.append(name)
        else:
            non_blocked[name] = non_uid_users[name]
    logging.info(f"Failed users: {len(blocked)}, {blocked[:6]}...")

    for current_name, non_uid_obj_id in non_blocked.items():
        uid = await ReqFreLimitApi.get_uid_by_name(current_name)
        if not uid:
            await redis_cache.set(
                key=f"{block_key_prefix}{current_name}",
                value="f",
                timeout=3600*24*random.randint(4, 7)
            )
            logging.warning(f"Cannot get uid by name: `{current_name}`")
            continue

        # 检查该uid是否在表里已存在, 如果不存在，则直接写入
        duplicated = await execute("select id, uid, name, face from biliuser where uid = %s;", uid)
        if not duplicated:
            r = await execute("update biliuser set uid=%s where id=%s;", (uid, non_uid_obj_id), _commit=True)
            logging.info(f"User obj updated! {current_name}({uid}), obj_id: {non_uid_obj_id}, r: {r}")
            continue

        logging.info(f"User {current_name}({uid}) duplicated, now fix it. ")
        has_uid_user_obj_id, uid, name, face = duplicated[0]

        # 有两个user_obj
        # 1.先把旧的existed_user_obj的name更新
        await execute("update biliuser set name=%s where id=%s", (current_name, has_uid_user_obj_id), _commit=True)

        # 2.迁移所有的raffle记录
        r = await execute(
            "update raffle set sender_obj_id=%s where sender_obj_id=%s;",
            (has_uid_user_obj_id, non_uid_obj_id),
            _commit=True
        )
        r2 = await execute(
            "update raffle set winner_obj_id=%s where winner_obj_id=%s;",
            (has_uid_user_obj_id, non_uid_obj_id),
            _commit=True
        )
        # 3.迁移guard
        r3 = await execute(
            "update guard set sender_obj_id=%s where sender_obj_id=%s;",
            (has_uid_user_obj_id, non_uid_obj_id),
            _commit=True
        )
        # 4.删除空的user_obj
        r4 = await execute(
            "delete from biliuser where id=%s;",
            (non_uid_obj_id, ),
            _commit=True
        )
        logging.info(f"Update {current_name}({uid}) done! sender: {r}, winner: {r2}, guard: {r3}, del: {r4}")


async def main():
    start_time = time.time()
    conn = await aiomysql.connect(
        host=MYSQL_CONFIG["host"],
        port=MYSQL_CONFIG["port"],
        user=MYSQL_CONFIG["user"],
        password=MYSQL_CONFIG["password"],
        db=MYSQL_CONFIG["database"]
    )

    async def execute(*args, _commit=False, **kwargs):
        async with conn.cursor() as cursor:
            await cursor.execute(*args, **kwargs)
            if _commit:
                await conn.commit()
            sql = args[0]
            if sql.startswith("select"):
                return await cursor.fetchall()
            return cursor.rowcount

    try:
        await fix_missed_uid(execute)
    except Exception as e:
        logging.info(f"FIX_DATA Error: {e}\n{traceback.format_exc()}")

    conn.close()
    cost = time.time() - start_time
    logging.info(f"Execute finished, cost: {cost/60:.3f} min.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
