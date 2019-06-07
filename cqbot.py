import os
import sys
import asyncio
import time
from random import random
import requests
import json
from utils.ws import ReConnectingWsClient
import logging
from math import floor

from cqhttp import CQHttp
from threading import Thread

log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
log_file_handler = logging.FileHandler(os.path.join("./log", "cqbot.log"), encoding="utf-8")
log_file_handler.setFormatter(log_format)
logger = logging.getLogger("cqbot")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
logger.addHandler(log_file_handler)
logging = logger


HANSY_LIVE_ROOM_ID = 2516117
LAST_NOTICE_ALL_TIME = time.time() - 7200
hansy_group_id_list = [
    159855203,  # test
    883237694,  # guard
    436496941,
    591691708,
]
bot = CQHttp(api_root='http://127.0.0.1:5700/', access_token='123456', secret='654321')


class WsApi(object):
    BILI_WS_URI = "ws://broadcastlv.chat.bilibili.com:2244/sub"
    PACKAGE_HEADER_LENGTH = 16
    CONST_MESSAGE = 7
    CONST_HEART_BEAT = 2

    @classmethod
    def generate_packet(cls, action, payload=""):
        payload = payload.encode("utf-8")
        packet_length = len(payload) + cls.PACKAGE_HEADER_LENGTH
        buff = bytearray(cls.PACKAGE_HEADER_LENGTH)
        # package length
        buff[0] = (packet_length >> 24) & 0xFF
        buff[1] = (packet_length >> 16) & 0xFF
        buff[2] = (packet_length >> 8) & 0xFF
        buff[3] = packet_length & 0xFF
        # migic & version
        buff[4] = 0
        buff[5] = 16
        buff[6] = 0
        buff[7] = 1
        # action
        buff[8] = 0
        buff[9] = 0
        buff[10] = 0
        buff[11] = action
        # migic parma
        buff[12] = 0
        buff[13] = 0
        buff[14] = 0
        buff[15] = 1
        return bytes(buff + payload)

    @classmethod
    def gen_heart_beat_pkg(cls):
        return cls.generate_packet(cls.CONST_HEART_BEAT)

    @classmethod
    def gen_join_room_pkg(cls, room_id):
        uid = int(1E15 + floor(2E15 * random()))
        package = '{"uid":%s,"roomid":%s}' % (uid, room_id)
        return cls.generate_packet(cls.CONST_MESSAGE, package)

    @classmethod
    def parse_msg(cls, message):
        msg_list = []
        while message:
            length = (message[0] << 24) + (message[1] << 16) + (message[2] << 8) + message[3]
            current_msg = message[:length]
            message = message[length:]
            if len(current_msg) > 16 and current_msg[16] != 0:
                try:
                    msg = current_msg[16:].decode("utf-8", errors="ignore")
                    msg_list.append(json.loads(msg))
                except Exception as e:
                    print("e: %s, m: %s" % (e, current_msg))
        return msg_list


async def __start_ws():
    def at_all_for_hansy(test=False):
        url = "https://api.live.bilibili.com/AppRoom/index?platform=android&room_id=2516117"
        headers = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/webp,image/apng,*/*;q=0.8"
            ),
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/70.0.3538.110 Safari/537.36"
            ),
        }
        try:
            r = requests.get(url=url, headers=headers)
            if r.status_code != 200:
                raise Exception("Error status code!")
            result = json.loads(r.content.decode("utf-8"))
            title = result.get("data", {}).get("title")
            image = result.get("data", {}).get("cover")
        except Exception as e:
            logging.exception("Error when get live room info: %s" % e, exc_info=True)
            title = "珩心小姐姐开播啦！快来围观"
            image = "https://i1.hdslb.com/bfs/archive/a6a3d6f3d3582fd5172f6f829c0fe5522705e399.jpg"

        content = "这里是一只易燃易咆哮的小狮子，宝物是糖果锤！嗷呜(っ*´□`)っ~不关注我的通通都要被一！口！吃！掉！"

        groups = hansy_group_id_list[:1] if test else hansy_group_id_list
        for group_id in groups:
            message = "[CQ:share,url=https://live.bilibili.com/2516117,title=%s,content=%s,image=%s]" % (
                title, content, image
            )
            bot.send(context={"message_type": "group", "group_id": group_id}, message=message)

            message = "[CQ:at,qq=all] \n直播啦！！快来听泡泡唱歌咯，本次直播主题：\n%s" % title
            bot.send(context={"message_type": "group", "group_id": group_id}, message=message)

    async def on_connect(ws):
        logging.info("connected.")
        await ws.send(WsApi.gen_join_room_pkg(HANSY_LIVE_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):
        global LAST_NOTICE_ALL_TIME

        for m in WsApi.parse_msg(message):
            cmd = m.get("cmd")
            if cmd == "LIVE":

                if time.time() - LAST_NOTICE_ALL_TIME > 1800:
                    at_all_for_hansy()
                else:
                    logging.error("Notice to freq!")

                LAST_NOTICE_ALL_TIME = time.time()

            elif cmd.startswith("DANMU_MSG"):
                info = m.get("info", {})
                msg = str(info[1])
                uid = info[2][0]

                logging.debug("Danmaku received: %s -> %s" % (uid, msg))

                if uid == 20932326:
                    if msg == "测试通知":
                        if time.time() - LAST_NOTICE_ALL_TIME > 1800:
                            at_all_for_hansy(test=True)
                        else:
                            logging.error("Notice to freq! test.")
                        LAST_NOTICE_ALL_TIME = time.time()
                    if msg == "重置通知":
                        LAST_NOTICE_ALL_TIME = time.time() - 7200

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Hansy ws stated.")
    while True:
        await asyncio.sleep(10)


def monitor_danmaku():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(__start_ws())


Thread(target=monitor_danmaku, daemon=True).start()


@bot.on_message()
def handle_msg(context):
    if context["message_type"] == "group":
        sender = context["sender"]
        user_id = sender["user_id"]
        user_nickname = sender["nickname"]
        title = sender.get("title", "--")
        card = sender.get("card",  "--")

        group_id = context["group_id"]
        msg = context["raw_message"]

        logging.info("Group message received: group_%s [%s][%s](%s qq: %s) -> %s"
                     % (group_id, title, card, user_nickname, user_id, msg))

        msg = msg.replace("！", "!").replace(" ", "").replace("　", "")
        if msg.startswith("!"):
            postfix = msg.split("睡觉")[-1].lower()
            if postfix[-1] not in ("s", "m", "h"):
                return {}

            try:
                duration = abs(int(postfix[:-1]))
                assert duration > 0
            except Exception:
                return {}

            if postfix[-1] == "m":
                duration *= 60
            elif postfix[-1] == "h":
                duration *= 3600

            bot.set_group_ban(group_id=group_id, user_id=user_id, duration=duration)

        elif msg == "一言":
            try:
                r = requests.get("https://v1.hitokoto.cn/", timeout=10)
                if r.status_code != 200:
                    return {}
                data = r.content.decode("utf-8")
                response = json.loads(data).get("hitokoto")

                bot.send_group_msg(group_id=group_id, message=response)
            except Exception:
                pass

    elif context["message_type"] == "private":
        user_id = context["sender"]["user_id"]
        user_nickname = context["sender"]["nickname"]
        msg = context["raw_message"]
        logging.info("Private message received: %s(qq: %s) -> %s" % (user_nickname, user_id, msg))

        if msg.startswith("起床"):
            try:
                group_id = int(msg[2:])
            except Exception:
                group_id = 0

            if group_id not in hansy_group_id_list:
                bot.send_private_msg(user_id=user_id, message="您输入的口令有误。若要解除禁言，请输入“起床+群号”， 如：“起床436496941”")
            else:
                bot.set_group_ban(group_id=group_id, user_id=user_id, duration=0)
        return {}


@bot.on_notice()
def handle_group_increase(context):
    """
    {
        'notice_type': 'group_increase',
        'sub_type': 'approve',
        'self_id': 2254494518,
        'user_id': 80873436,
        'time': 1559880184,
        'group_id': 159855203,
        'post_type': 'notice',
        'operator_id': 310300788
    }
    """
    print("handle_group_increase", context)

    if context["notice_type"] == 'group_increase' and context["group_id"] == 436496941:
        user_id = context["user_id"]
        member = bot.get_group_member_info(group_id=436496941, user_id=user_id)
        nickname = member["nickname"]

        bot.set_group_card(group_id=436496941, user_id=user_id, card="✿泡泡┊" + nickname)

        message = (
            "欢迎[CQ:at,qq=%s] 进入泡泡小黄鸡养殖场！\n\n"
            "群名片格式；✿泡泡┊ +你的昵称，稽气人已经自动为你修改~ \n\n"
            "进群记得发个言哦，否则有可能会被当机器人清理掉，很可怕的哦~ "
            "从今天开始一起跟泡泡守护小黄鸡呀！叽叽叽~"
        ) % user_id
        bot.send_group_msg(group_id=436496941, message=message)

    return {}


bot.run(host='127.0.0.1', port=8080)
