import time
import datetime
from typing import List, Union, Tuple
from db.queries import queries, LTUser
from utils.dao import UserRaffleRecord
from utils.covert import gen_time_prompt
from utils.biliapi import BiliApi


async def get_lt_user_status(user_id: int) -> Tuple[bool, str]:
    lt_user = await queries.get_lt_user_by_uid(user_id=user_id)
    if not lt_user:
        return False, f"{user_id}未登录宝藏站点。"

    user_prompt_title = f"{lt_user.name}（uid: {user_id}）"
    if not lt_user.available:
        return False, f"{user_prompt_title}登录已过期，请重新登录。"

    start_time = time.time()
    rows = await UserRaffleRecord.get_by_user_id(user_id=user_id)

    if lt_user.last_accept_time:
        last_accept_interval = (datetime.datetime.now() - lt_user.last_accept_time).total_seconds()
    else:
        last_accept_interval = 0xFFFFFFFF
    last_accept = gen_time_prompt(int(last_accept_interval))
    user_prompt = f"{user_prompt_title}\n最后一次抽奖时间：{last_accept}"

    if lt_user.is_blocked:
        interval_seconds = (datetime.datetime.now() - lt_user.blocked_time).total_seconds()
        return False, f"{user_prompt}\n{gen_time_prompt(int(interval_seconds))}发现你被关进了小黑屋。"

    process_time = time.time() - start_time
    calc = {}
    total_intimacy = 0
    raffle_count = len(rows)
    for row in rows:
        gift_name, raffle_id, intimacy = row.split("$")
        intimacy = int(intimacy)
        if gift_name not in calc:
            calc[gift_name] = 1
        else:
            calc[gift_name] += 1

        if gift_name != "宝箱":
            total_intimacy += intimacy

    def sort_func(r):
        priority_map = {
            "宝箱": 0,
            "总督": 1,
            "提督": 2,
            "舰长": 3,
        }
        return priority_map.get(r[0], 4)

    postfix = []
    for gift_name, times in sorted([(gift_name, times) for gift_name, times in calc.items()], key=sort_func):
        postfix.append(f"{gift_name}: {times}次")
    if postfix:
        postfix = f"{'-' * 20}\n" + "、".join(postfix) + "。"
    else:
        postfix = ""

    prompt = [
        f"{user_prompt}，现在正常领取辣条中。\n",
        f"24小时内累计抽奖{raffle_count}次，共获得{total_intimacy}辣条。\n",
        postfix,
        f"\n处理时间：{process_time:.3f}"
    ]
    return True, "".join(prompt)


async def add_user_by_account(
        account: str,
        password: str,
        notice_email: str = None
) -> Tuple[bool, Union[str, LTUser]]:

    lt_users = await queries.get_all_lt_user()
    lt_user = None
    for u in lt_users:
        if u.account == account:
            if u.available:
                u.password = password
                update_fields = ["password"]

                if notice_email is not None:
                    u.notice_email = notice_email
                    update_fields.append("notice_email")

                await queries.update_lt_user(u, fields=update_fields)
                return True, u
            else:
                lt_user = u
                break

    flag, r = await BiliApi.login(
        account,
        password,
        cookie=getattr(lt_user, "cookie", None),
        access_token=getattr(lt_user, "access_token", None),
        refresh_token=getattr(lt_user, "refresh_token", None),
    )
    if not flag:
        return False, f"登录失败，请使用扫码登录！（哔哩服务器返回结果：{r}）"

    lt_user = await queries.upsert_lt_user(
        account=account,
        password=password,
        notice_email=notice_email,
        **r,
    )
    return True, lt_user
