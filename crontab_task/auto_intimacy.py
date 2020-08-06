import asyncio
from typing import List, Tuple
from config.log4 import config_logger
from utils.biliapi import BiliApi
from src.api.bili import BiliPrivateApi
from src.api.schemas import UserMedalInfo, BagItem
from src.db.queries.queries import queries, LTUser
from src.db.queries.cron_action import record_send_gift

logging = config_logger("auto_intimacy")


NON_LIMIT_UID_LIST = (
    20932326,  # dd
    39748080,  # 录屏
    312186483,  # 桃子
    87301592,  # 酋长
)


async def send_gift(user: LTUser, medal_name: str):
    cookie = user.cookie
    private_api = BiliPrivateApi(req_user=user)

    target_medal = None
    medals: List[UserMedalInfo] = await private_api.get_user_owned_medals()
    for medal in medals:
        if medal.medal_name == medal_name and medal.roomid:
            target_medal = medal
            break
    if not target_medal:
        return
    logging.info(f"\n{'-'*80}\n开始处理：{user} -> {medal_name}\n\t{target_medal}")

    live_room_id = await BiliApi.force_get_real_room_id(target_medal.roomid)
    logging.info(f"今日剩余亲密度: {target_medal.left_intimacy}")

    bag_list = await private_api.get_bag_list()
    available_bags = sorted([
        bag for bag in bag_list
        if bag.gift_name == "辣条" and bag.expire_at > 0
    ], key=lambda x: x.expire_at)

    # 获取背包中的辣条
    send_list: List[Tuple[int, BagItem]] = []
    left_intimacy = target_medal.left_intimacy
    for bag in available_bags:
        intimacy_single = 1
        need_send_gift_num = min(left_intimacy // intimacy_single, bag.gift_num)

        if need_send_gift_num > 0:
            send_list.append((need_send_gift_num, bag))
            left_intimacy -= intimacy_single * need_send_gift_num

        if left_intimacy <= 0:
            break

    # # 获取钱包 赠送银瓜子辣条
    # if user.uid in NON_LIMIT_UID_LIST and left_intimacy > 0:
    #     wallet_info = await BiliApi.get_wallet(cookie)
    #     silver = wallet_info.get("silver", 0)
    #     supplement_lt_num = min(silver // 100, left_intimacy)
    #     if supplement_lt_num > 0:
    #         send_list.append({
    #             "corner_mark": "银瓜子",
    #             "coin_type": "silver",
    #             "gift_num": supplement_lt_num,
    #             "bag_id": 0,
    #             "gift_id": 1,
    #         })
    #         left_intimacy -= supplement_lt_num

    for send_num, bag in send_list:
        flag, data = await BiliApi.send_gift(
            gift_id=bag.gift_id,
            gift_num=send_num,
            coin_type=None,
            bag_id=bag.bag_id,
            ruid=target_medal.target_id,
            live_room_id=live_room_id,
            cookie=user.cookie,
        )
        if flag:
            await record_send_gift(
                user_id=user.uid,
                bag_id=bag.bag_id,
                gift_id=bag.gift_id,
                live_room_id=live_room_id,
                medal=medal_name,
                gift_name=bag.gift_name,
                gift_count=send_num,
                expire_at=bag.expire_at,
                corner_mark=bag.corner_mark,
                purpose="自动升级勋章",
            )
        else:
            logging.info(f"Send failed, msg: {data.get('message', 'unknown')}")

    send_msg = "\n".join([f"{s.corner_mark}辣条 * {s.gift_num}" for _, s in send_list])
    logging.info(f"赠送礼物列表:\n\n{send_msg}\n\n{user} 剩余亲密度: {left_intimacy}\n{'-'*80}")


async def main():
    lt_users: List[LTUser] = await queries.get_lt_user_by(available=True)
    # lt_users = [await queries.get_lt_user_by_uid("DD")]
    for lt_user in lt_users:
        for medal in lt_user.send_medals:
            await send_gift(user=lt_user, medal_name=medal)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
