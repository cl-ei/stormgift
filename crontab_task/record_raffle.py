import asyncio
from utils.db_raw_query import AsyncMySQL
from utils.reconstruction_model import Guard, Raffle
from config.log4 import crontab_task_logger as logging
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor


async def sync_guard():
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
    data = await RedisGuard.get_all()
    for d in data:
        await Guard.create(**d)
        logging.info(f"Saved: G:{d['gift_id']} {d['sender_name']} -> {d['room_id']}")


async def sync_raffle():
    raffles = await RedisRaffle.get_all()
    done_ids = []
    for raffle in raffles:
        done_ids.append(raffle["raffle_id"])
        if "winner_uid" in raffle and "winner_name" in raffle:
            r = await Raffle.create(**raffle)
        else:
            r = await Raffle.record_raffle_before_result(**raffle)
        logging.info(f"Saved: T:{raffle['raffle_id']} {r.id}")
    await RedisRaffle.delete(*done_ids)


async def main():
    await sync_guard()
    await sync_raffle()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
