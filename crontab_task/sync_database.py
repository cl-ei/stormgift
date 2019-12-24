import os
import time
import random
import logging
import asyncio
import aiomysql
import datetime
import configparser
from utils.biliapi import BiliApi
from utils.db_raw_query import AsyncMySQL
from utils.highlevel_api import ReqFreLimitApi
from utils.dao import ValuableLiveRoom, redis_cache
from config.log4 import lt_db_sync_logger as logging
from utils.reconstruction_model import objects, BiliUser, Raffle, Guard


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
    async def sync_lt_user_cookie(cls):
        query = await XNodeMySql.execute("select * from ltusercookie order by id desc;")
        for row in query:
            row_sql = ",".join(["%s" for _ in range(len(query[0]))])
            sql = f"INSERT INTO ltusercookie VALUES({row_sql});"
            await AsyncMySQL.execute(sql, row, _commit=True)

    @classmethod
    async def run(cls):
        start_time = time.time()
        logging.info(f"Start Sync Database...")
        await cls.sync_lt_user_cookie()

        cost = time.time() - start_time
        logging.info(f"Execute finished, cost: {cost/60:.3f} min.\n\n")


loop.run_until_complete(SyncTool.run())
