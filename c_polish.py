import asyncio
from typing import *
from config.log4 import get_logger
from utils.biliapi import BiliApi
from src.api.bili import BiliPrivateApi
from src.api.schemas import UserMedalInfo, BagItem
from src.db.queries.queries import queries, LTUser

logging = get_logger("c_polish")


def get_gift_args(hearts: List[BagItem], count: int) -> List[Dict]:
    gift_args = []
    for heart in hearts:
        while heart.gift_num > 0:
            gift_args.append({
                "gift_id": heart.gift_id,
                "gift_num": 1,
                "coin_type": None,
                "bag_id": heart.bag_id,
            })
            heart.gift_num -= 1
            if len(gift_args) >= count:
                return gift_args
    return gift_args


async def polish(user: LTUser, medals: List[UserMedalInfo]):
    if not medals:
        return

    api = BiliPrivateApi(user)

    bag_list = await api.get_bag_list()
    hearts = [b for b in bag_list if b.gift_name == "小心心"]
    hearts.sort(key=lambda x: x.expire_at)
    gift_args = get_gift_args(hearts, len(medals))

    available_medals = medals[:len(gift_args)]
    for i, medal in enumerate(available_medals):
        args = gift_args[i]
        args.update({
            "ruid": medal.target_id,
            "live_room_id": medal.roomid,
            "cookie": user.cookie,
        })
        print(f"send gift: {args}")

        flag, data = await BiliApi.send_gift(**args)
        logging.info(f"user({user}) shine [{medal.medal_name}] flag: {flag}, \n\tdata: {data}")


async def main():
    lt_users: List[LTUser] = await queries.get_lt_user_by(available=True)
    # lt_users = [await queries.get_lt_user_by_uid("DD")]
    for user in lt_users:
        if user.shine_medal_policy == 0:
            continue

        api = BiliPrivateApi(req_user=user)
        medals = await api.get_user_owned_medals()
        dark_medals = [m for m in medals if m.is_lighted == 0 and m.target_id != user.user_id]
        if not dark_medals:
            continue

        dark_medals.sort(key=lambda x: x.score, reverse=True)
        if user.shine_medal_policy == 1:        # 擦亮全部
            await polish(user, dark_medals)
        elif user.shine_medal_policy == 2:      # 擦亮最高的n个
            await polish(user, dark_medals[:user.shine_medal_count])
        else:                                   # 擦亮指定的
            sh_medals = [m for m in dark_medals if m.medal_name in user.shine_medals]
            await polish(user, sh_medals)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
