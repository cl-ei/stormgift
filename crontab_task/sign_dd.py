import asyncio
from config import g
from random import choice
from utils.biliapi import BiliApi
from db.queries import LTUser, List, queries


async def get_aids():
    url = "https://api.bilibili.com/x/web-interface/newlist?rid=96&type=0&pn=1&ps=50"
    flag, data = await BiliApi.get(url=url, check_error_code=True)
    if not flag:
        return []
    return [a["aid"] for a in data["data"]["archives"]]


async def send_coin(user, aids):
    flag, tasks = await BiliApi.fetch_bili_main_tasks(cookie=user.cookie)
    need_send_coin = int(5 - tasks["coins_av"] / 10)
    if need_send_coin < 1:
        return
    print(f"{user.name} Need send coin: {need_send_coin}")
    coin_send = 0
    for try_times in range(20):
        select_one = choice(aids)
        flag, msg = await BiliApi.add_coin(aid=select_one, cookie=user.cookie)
        if flag:
            coin_send += 1
        else:
            print(f"coin send Failed! {msg}")

        if coin_send >= need_send_coin:
            break


async def share(user, aids):
    error = ""
    for try_times in range(20):
        flag, data = await BiliApi.share_video(aid=choice(aids), cookie=user.cookie)
        if flag and data["code"] == 0:
            return
        error = f"flag: {flag}, r: {data}"

    else:
        print(f"Error: {error}")


async def main():
    aids = await get_aids()
    for uid in ("TZ", "DD", g.BILI_UID_CZ):
        user = await queries.get_lt_user_by_uid(user_id=uid)
        await send_coin(user=user, aids=aids)
        await share(user=user, aids=aids)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
