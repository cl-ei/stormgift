import datetime
import time
import smtplib
import sys
import json
import logging
import asyncio
from email.mime.text import MIMEText


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
logger = logging.getLogger("do_sign")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)

if "linux" in sys.platform:
    file_handler = logging.FileHandler("/home/wwwroot/log/dosign.log")
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

logging = logger


def send_mail_notice(subject, to=""):
    to = to.strip()
    if not to:
        return

    with open("/home/wwwroot/stormgift/config/proj_config.json") as f:
        pass_word = json.load(f).get("mail_auth_pass", "") or ""

    user = "80873436@qq.com"
    from_addr = user

    msg = MIMEText("挂辣条异常")
    msg['Subject'] = subject or "-"
    msg['From'] = from_addr
    msg['To'] = to

    s = smtplib.SMTP_SSL("smtp.qq.com", 465)
    try:
        s.login(user, pass_word)
        s.sendmail(from_addr, to, msg.as_string())
    except Exception as e:
        logging.error(f"Cannot send email: {e}", exc_info=True)
    finally:
        s.quit()


async def main():
    logging.info(f"Start do sign task.")
    start_time = time.time()
    if "linux" in sys.platform:
        sys.path.append('/home/wwwroot/stormgift/')
    else:
        sys.path.append('../')

    from utils.biliapi import BiliApi

    with open("/home/wwwroot/stormgift/data/cookie.json") as f:
        cookies = json.load(f).get("RAW_COOKIE_LIST", []) or []

    vip_list = []
    available_cookies = []
    invalid_cookies = []
    for index, cookie in enumerate(cookies):
        await asyncio.sleep(0.5)
        r, data = await BiliApi.get_if_user_is_live_vip(cookie)
        if r and data:
            vip_list.append(cookie)

        await asyncio.sleep(0.5)
        r, data = await BiliApi.do_sign(cookie)
        if not r and "登录" in data:
            invalid_cookies.append(cookie)

            email_addr = ""
            for c in cookie.split(';'):
                if "notice_email" in c:
                    email_addr = c.split("=")[-1].strip()
                    break
            send_mail_notice(f"挂辣条-登录信息已过期：\n{cookie.split(';')[0]}", email_addr)

        else:
            available_cookies.append(cookie)

        await asyncio.sleep(0.5)
        r, data = await BiliApi.do_sign_group(cookie)
        if not r:
            logging.error(f"Sign group failed, {index}-{cookie.split(';')[0]}: {data}")

        await asyncio.sleep(0.5)
        await BiliApi.do_sign_double_watch(cookie)

        if "20932326" in cookie:
            await asyncio.sleep(0.5)
            await BiliApi.silver_to_coin(cookie)

    with open("/home/wwwroot/stormgift/data/heartbeat_cookies.json", "wb") as f:
        f.write(json.dumps({"RAW_COOKIE_LIST": vip_list}, ensure_ascii=False).encode("utf-8"))

    if invalid_cookies and datetime.datetime.now().hour > 18:
        with open("/home/wwwroot/stormgift/data/cookies.json", "wb") as f:
            f.write(json.dumps({"RAW_COOKIE_LIST": available_cookies}, ensure_ascii=False, indent=2).encode("utf-8"))
        logging.info(f"RAW_COOKIE_LIST updated!")

    logging.info(f"Do sign task done. cost: {int((time.time() - start_time) *1000)} ms.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

