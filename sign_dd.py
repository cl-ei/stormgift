import asyncio
import datetime
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator


MEDAL_ID_小孩梓 = 13139


async def main():
    user = await DBCookieOperator.get_by_uid("DD")
    flag, wear_medal = await BiliApi.get_wear_medal(cookie=user.cookie)
    await BiliApi.wear_medal(cookie=user.cookie, medal_id=MEDAL_ID_小孩梓)
    flag, msg = await BiliApi.send_danmaku(message="打卡", room_id=80397, cookie=user.cookie)
    print(f"Send danmaku: {flag}, msg: {msg}")
    if wear_medal:
        flag, msg = await BiliApi.wear_medal(cookie=user.cookie, medal_id=wear_medal["medal_id"])
        print(F"Final wear: {wear_medal['medal_name']}: {flag}, msg: {msg}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
