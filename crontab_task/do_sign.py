import time
import json
import asyncio
import smtplib
from utils.biliapi import BiliApi
from email.mime.text import MIMEText
from config.log4 import crontab_task_logger as logging


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

    with open("data/valid_cookies.txt") as f:
        cookies = [_.strip() for _ in f.readlines()]

    for index, cookie in enumerate(cookies):
        await asyncio.sleep(0.5)
        await BiliApi.do_sign(cookie)

        # if not r and "登录" in data:
        #
        #     email_addr = ""
        #     for c in cookie.split(';'):
        #         if "notice_email" in c:
        #             email_addr = c.split("=")[-1].strip()
        #             break
        #     send_mail_notice(f"挂辣条-登录信息已过期：\n{cookie.split(';')[0]}", email_addr)

        await asyncio.sleep(0.5)
        r, data = await BiliApi.do_sign_group(cookie)
        if not r:
            logging.error(f"Sign group failed, {index}-{cookie.split(';')[0]}: {data}")

        await asyncio.sleep(0.5)
        await BiliApi.do_sign_double_watch(cookie)

        if "20932326" in cookie:
            await asyncio.sleep(0.5)
            await BiliApi.silver_to_coin(cookie)

    logging.info(f"Do sign task done. cost: {int((time.time() - start_time) *1000)} ms.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

