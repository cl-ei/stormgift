import sys; sys.path.append('../')
import asyncio
from utils.biliapi import BiliApi
from data import COOKIE_LP, COOKIE_DD
SEND_CONFIG = {
    39748080: "电磁泡",
    20932326: "电磁泡",
}


async def send_gift(cookie):
    r = await BiliApi.get_medal_info_list(cookie)
    if not r:
        return
    uid = r[0]["uid"]
    target_model = [_ for _ in r if _["medal_name"] == SEND_CONFIG[uid]]
    if not target_model:
        return
    target_model = target_model[0]
    print(target_model["medal_name"])

    live_room_id = target_model["roomid"]
    ruid = target_model["anchorInfo"]["uid"]

    today_feed = target_model["todayFeed"]
    day_limit = target_model["dayLimit"]
    left_intimacy = day_limit - today_feed
    print(f"left_intimacy: {left_intimacy}")

    bag_list = await BiliApi.get_bag_list(cookie)
    gift_today = []
    gift_lt = []
    gift_bkl = []
    for gift in bag_list:
        if gift["corner_mark"] == "今天":
            gift_today.append(gift)
        elif gift["gift_name"] == "辣条":
            gift_lt.append(gift)
        elif gift["gift_name"] == "B坷垃":
            gift_bkl.append(gift)
    gift_lt.sort(key=lambda x: x["expire_at"])
    gift_bkl.sort(key=lambda x: x["expire_at"])
    can_send_bag = gift_today + gift_bkl + gift_lt
    print(can_send_bag)

    send_list = []
    for gift in can_send_bag:
        if gift["gift_name"] == "辣条":
            intimacy_single = 1
        elif gift["gift_name"] == "B坷垃":
            intimacy_single = 99
        else:
            continue

        need_send_gift_num = min(left_intimacy // intimacy_single, gift["gift_num"])
        send_list.append({
            "coin_type": None,
            "gift_num": need_send_gift_num,
            "bag_id": gift["bag_id"],
            "gift_id": gift["gift_id"],
        })
        left_intimacy -= intimacy_single*need_send_gift_num
        if left_intimacy <= 0:
            break

    if left_intimacy > 0:
        wallet_info = await BiliApi.get_wallet(cookie)
        silver = wallet_info.get("silver", 0)
        supplement_lt_num = min(silver // 100, left_intimacy)
        if supplement_lt_num > 0:
            send_list.append({
                "coin_type": "silver",
                "gift_num": supplement_lt_num,
                "bag_id": 0,
                "gift_id": 1,
            })

    for gift in send_list:
        r = await BiliApi.send_gift(
            gift["gift_id"], gift["gift_num"], gift["coin_type"], gift["bag_id"], ruid, live_room_id, cookie
        )
        print(f"Send gift: {gift}\n\tr: {r}")
    print(f"Final left intimacy: {left_intimacy}")


async def main():
    await send_gift(COOKIE_LP)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
