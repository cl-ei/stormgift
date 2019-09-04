import sys
import asyncio
from config.log4 import crontab_task_logger as logging
from utils.highlevel_api import DBCookieOperator


async def send_gift(cookie, medal, user_name=""):
    from utils.biliapi import BiliApi

    r = await BiliApi.get_medal_info_list(cookie)
    if not r:
        return

    uid = r[0]["uid"]
    target_model = [_ for _ in r if _["medal_name"] == medal]
    if not target_model:
        return
    target_model = target_model[0]
    logging.info(
        f"{'-'*80}\n"
        f"开始处理：{uid} {user_name} -> {target_model['medal_name']}"
    )

    live_room_id = await BiliApi.force_get_real_room_id(target_model["roomid"])
    ruid = target_model["anchorInfo"]["uid"]

    today_feed = target_model["todayFeed"]
    day_limit = target_model["dayLimit"]
    left_intimacy = day_limit - today_feed
    logging.info(f"今日剩余亲密度: {left_intimacy}")

    bag_list = await BiliApi.get_bag_list(cookie)
    gift_today = []
    gift_lt = []

    for gift in bag_list:
        if gift["corner_mark"] == "今天":
            gift_today.append(gift)
        elif gift["gift_name"] == "辣条":
            gift_lt.append(gift)

    gift_lt.sort(key=lambda x: x["expire_at"])
    can_send_bag = gift_today + gift_lt

    send_list = []
    for gift in can_send_bag:
        if gift["gift_name"] == "辣条":
            intimacy_single = 1
        else:
            continue

        need_send_gift_num = min(left_intimacy // intimacy_single, gift["gift_num"])
        if need_send_gift_num > 0:
            send_list.append({
                "corner_mark": gift["corner_mark"],
                "coin_type": None,
                "gift_num": need_send_gift_num,
                "bag_id": gift["bag_id"],
                "gift_id": gift["gift_id"],
            })
            left_intimacy -= intimacy_single * need_send_gift_num

        if left_intimacy <= 0:
            break

    if left_intimacy > 0:
        wallet_info = await BiliApi.get_wallet(cookie)
        silver = wallet_info.get("silver", 0)
        supplement_lt_num = min(silver // 100, left_intimacy)
        if supplement_lt_num > 0:
            send_list.append({
                "corner_mark": "银瓜子",
                "coin_type": "silver",
                "gift_num": supplement_lt_num,
                "bag_id": 0,
                "gift_id": 1,
            })
            left_intimacy -= supplement_lt_num

    for gift in send_list:
        # flag, data = await BiliApi.send_gift(
        #     gift["gift_id"], gift["gift_num"], gift["coin_type"], gift["bag_id"], ruid, live_room_id, cookie
        # )
        # if not flag:
        #     logging.info(f"Send failed, msg: {data.get('message', 'unknown')}")
        pass

    send_msg = "\n".join([f"{s['corner_mark']}辣条 * {s['gift_num']}" for s in send_list])
    logging.info(
        f"赠送礼物列表:\n"
        f"{send_msg}\n"
        f"{user_name} 剩余亲密度: {left_intimacy}\n"
        f"{'-'}*80"
    )


async def main():
    obj = await DBCookieOperator.get_by_uid(20932326)
    if obj:
        await send_gift(cookie=obj.cookie, medal="小孩梓", user_name="打盹")
        await send_gift(cookie=obj.cookie, medal="电磁泡", user_name="打盹")

    obj = await DBCookieOperator.get_by_uid(39748080)
    if obj:
        await send_gift(cookie=obj.cookie, medal="电磁泡", user_name="录屏")

    obj = await DBCookieOperator.get_by_uid(312186483)
    if obj:
        await send_gift(cookie=obj.cookie, medal="小夭精", user_name="桃子")

    obj = await DBCookieOperator.get_by_uid(87301592)
    if obj:
        await send_gift(cookie=obj.cookie, medal="电磁泡", user_name="村长")

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
