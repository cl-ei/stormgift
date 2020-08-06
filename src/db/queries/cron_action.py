import datetime
from src.db.clients.mongo import db
from src.db.models.cron_action import (
    SilverBoxRec,
    UserActRec,
)


async def get_or_create_today_rec(user_id: int) -> UserActRec:
    today = f"{datetime.date.today()}"
    query = {"user_id": user_id, "date": today}
    rec: UserActRec = await UserActRec.find_one(db, query)
    if rec is None:
        rec = UserActRec(user_id=user_id, date=today)
    return rec


async def record_sign(user_id: int) -> UserActRec:
    rec = await get_or_create_today_rec(user_id)
    rec.sign_time = datetime.datetime.now()
    return await rec.save(db, fields=("sign_time", ))


async def record_sign_group(user_id: int, text: str) -> UserActRec:
    rec = await get_or_create_today_rec(user_id)
    rec.sign_group_time = datetime.datetime.now()
    rec.sign_group_text = text
    return await rec.save(db, fields=("sign_group_time", "sign_group_text"))


async def record_heart_beat(user_id: int) -> UserActRec:
    rec = await get_or_create_today_rec(user_id)
    rec.heart_beat_count += 1
    rec.last_heart_beat = datetime.datetime.now()
    return await rec.save(db, fields=("heart_beat_count", "last_heart_beat"))


async def record_silver_box(user_id: int, text: str) -> UserActRec:
    box = SilverBoxRec(
        accept_time=datetime.datetime.now(),
        response_text=text,
    )
    rec = await get_or_create_today_rec(user_id)
    rec.silver_box.append(box)
    return await rec.save(db, fields=("silver_box",))
