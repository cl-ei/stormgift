import asyncio
from config.log4 import crontab_task_logger as logging
from utils.biliapi import BiliApi


async def check_single_cookie(c):
    """

    :param c:
    :return: valid, is_vip, cookie
    """
    valid_keys = 0

    DedeUserID = 0
    SESSDATA = ""
    bili_jct = ""

    for kv in c.replace(" ", "").replace("\n", "").split(";"):
        if "DedeUserID" in kv:
            DedeUserID = int(kv.split("=")[-1])
            valid_keys += 1

        if "SESSDATA" in kv:
            SESSDATA = kv.split("=")[-1]
            valid_keys += 1

        if "bili_jct" in kv:
            bili_jct = kv.split("=")[-1]
            valid_keys += 1

    if valid_keys < 3:
        return False, False, ""

    cookie = f"DedeUserID={DedeUserID}; SESSDATA={SESSDATA}; bili_jct={bili_jct}"
    r, data = await BiliApi.get_if_user_is_live_vip(cookie, user_id=DedeUserID)
    if r:
        return True, data, cookie
    else:
        return False, False, ""


async def main():
    with open("data/cookies.txt", "r") as f:
        cookies = f.readlines()

    valid_cookies = []
    vip_cookies = []
    valid_raw_cookies = []
    for c in cookies:
        valid, is_vip, cookie = await check_single_cookie(c)
        if valid:
            valid_raw_cookies.append(c)

            valid_cookies.append(cookie)

            if is_vip:
                vip_cookies.append(cookie)

        await asyncio.sleep(0.5)

    with open("data/cookies.txt", "w") as f:
        f.write("\n".join(valid_raw_cookies))

    with open("data/valid_cookies.txt", "w") as f:
        f.write("\n".join(valid_cookies))

    with open("data/vip_cookies.txt", "w") as f:
        f.write("\n".join(vip_cookies))

    logging.info(
        f"Cookies synced: Raw cookies: {len(cookies)}, "
        f"valid: {len(valid_cookies)}, vip_cookies: {len(vip_cookies)}."
    )


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
