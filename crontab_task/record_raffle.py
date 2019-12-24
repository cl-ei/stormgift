import asyncio
from utils.db_raw_query import AsyncMySQL
from utils.reconstruction_model import Guard, Raffle
from config.log4 import crontab_task_logger as logging
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor, gen_x_node_redis


async def sync_guard(redis):
    """
     {'gift_id': 1790852,
         'room_id': 813364,
         'gift_name': '舰长',
         'sender_uid': 2954420,
         'sender_name': '愿世界平和',
         'sender_face': 'http://i2.hdslb.com/bfs/face/328714597f9641a1220366258ba844da62f66fc9.jpg',
         'created_time': datetime.datetime(2019, 12, 24, 19, 22, 28, 595228),
         'expire_time': datetime.datetime(2019, 12, 24, 19, 42, 27, 595228)
     }
    """
    data = await RedisGuard.get_all(redis=redis)
    for d in data:
        await Guard.create(**d)
        logging.info(f"Saved: G:{d['gift_id']} {d['sender_name']} -> {d['room_id']}")


async def sync_raffle(redis):
    raffles = await RedisRaffle.get_all(redis=redis)
    for raffle in raffles:
        raffle_id = raffle["raffle_id"]
        if "winner_uid" in raffle and "winner_name" in raffle:
            r = await Raffle.create(**raffle)
        else:
            r = await Raffle.record_raffle_before_result(**raffle)
        logging.info(f"Saved: T:{raffle['raffle_id']} {r.id}")
        await RedisRaffle.delete(raffle_id, redis=redis)


async def sync_anchor(redis):
     raffles = await RedisAnchor.get_all(redis=redis)


async def main():
    x_node_redis = await gen_x_node_redis()

    await sync_guard(x_node_redis)
    await sync_raffle(x_node_redis)

    # tears down.
    await x_node_redis.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
