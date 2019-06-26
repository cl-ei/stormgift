import re
import json
import time
import uuid
import logging
import requests
import datetime
import hashlib
import asyncio
import traceback
from random import choice
from cqhttp import CQHttp
from config import CQBOT
from utils.dao import CookieOperator, HansyQQGroupUserInfo
from config.log4 import cqbot_logger as logging


class Settings:
    LIVE_ROOM_ID = 2516117

    last_notice_time = time.time() - 7200
    last_prepare_time = time.time() - 7200

    TEST_GROUP_ID_LIST = [159855203, ]
    NOTICE_GROUP_ID_LIST = [
        159855203,  # test
        883237694,  # guard
        436496941,
        591691708,  # 禁言群
    ]


bot = CQHttp(**CQBOT)


class BotUtils:

    @classmethod
    def post_word_audio(cls, word, group_id):
        url = f"http://media.shanbay.com/audio/us/{word}.mp3"
        try:
            r = requests.get(url)
            assert r.status_code == 200
            file = f"{word}.mp3"
            with open(file, "wb") as f:
                f.write(r.content)

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Error happened in post_word_audio: {e}.\n{tb}"

            logging.exception(error_msg, exc_info=True)
            bot.send_group_msg(group_id=group_id, message=error_msg)

        else:
            bot.send_group_msg(group_id=group_id, message=f"[CQ:record,file={word}.mp3,magic=false]")

    @classmethod
    def proc_translation(cls, msg, group_id):
        word = msg[3:]
        YOUDAO_URL = "http://openapi.youdao.com/api"
        APP_KEY = "679aa6a74516f7c7"
        APP_SECRET = "mUJXnipoSAV8wzUs6yxUgnSZi6M2Ulbd"

        def encrypt(sign_str):
            hash_algorithm = hashlib.sha256()
            hash_algorithm.update(sign_str.encode('utf-8'))
            return hash_algorithm.hexdigest()

        def truncate(q):
            if q is None:
                return None
            size = len(q)
            return q if size <= 20 else q[0:10] + str(size) + q[size - 10:size]

        q = word
        data = {}
        data['from'] = 'EN'
        data['to'] = 'zh-CHS'
        data['signType'] = 'v3'
        curtime = str(int(time.time()))
        data['curtime'] = curtime
        salt = str(uuid.uuid1())
        signStr = APP_KEY + truncate(q) + salt + curtime + APP_SECRET
        sign = encrypt(signStr)
        data['appKey'] = APP_KEY
        data['q'] = q
        data['salt'] = salt
        data['sign'] = sign

        try:
            r = requests.post(
                YOUDAO_URL,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            assert r.status_code
            r = json.loads(r.content.decode("utf-8"))
            assert isinstance(r, dict)

            translation = r.get("translation", "")
            if not translation:
                raise Exception("No translation.")

            if len(word) > 20:
                word = word[:19] + "..."
                br = "\n"
                message = f"{word}：\n{br.join(translation)}"
            else:
                message = f"{word}：{', '.join(translation)}"

            explains = r.get("basic", {}).get("explains", []) or []
            if explains:
                message += "\n---------\n"
                message += "\n".join(explains)

            more = ""
            web = r.get("web", []) or []
            for w in web:
                if isinstance(w, dict):
                    more += f"\n{w['key']}：{w['value'][0]}"
            if more:
                message += f"\n\n更多:{more}"

            bot.send_group_msg(group_id=group_id, message=message)

        except Exception as e:
            logging.exception(f"Error: {e}")
            bot.send_group_msg(group_id=group_id, message=f"未找到“{word}”的释义 。")

    @staticmethod
    def get_song_id(song_name):

        songs = []
        no_salt_songs = []
        try:
            url = "http://music.163.com/api/search/pc"
            r = requests.post(url, data={"s": song_name, "type": 1, "limit": 50, "offset": 0})
            if r.status_code == 200:
                r = json.loads(r.content.decode("utf-8")).get("result", {}).get("songs", []) or []
                if isinstance(r, list):
                    no_salt_songs = r
                    songs.extend(r)

            time.sleep(0.3)
            r = requests.post(url, data={"s": song_name + " 管珩心", "type": 1, "limit": 50, "offset": 0})
            if r.status_code == 200:
                r = json.loads(r.content.decode("utf-8")).get("result", {}).get("songs", [])
                if isinstance(r, list):
                    songs.extend(r)

            assert songs

        except Exception:
            return None

        song_name = song_name.lower().strip()
        name_matched = []
        for song in songs:
            name = song.get("name").lower().strip()
            if (
                    name == song_name
                    or (len(name) < len(song_name) and name in song_name)
                    or (len(song_name) < len(name) and song_name in name)
            ):
                name_matched.append(song)

        filtered_songs = name_matched or no_salt_songs
        for song in filtered_songs:
            artist_names = "".join([artist.get("name").lower().strip() for artist in song.get("artists", [])])
            if "管珩心" in artist_names or "hansy" in artist_names or "泡泡" in artist_names:
                return song.get("id")

        return filtered_songs[0].get("id") if filtered_songs else None

    @classmethod
    def proc_one_sentence(cls, msg, group_id):
        try:
            r = requests.get("https://v1.hitokoto.cn/", timeout=10)
            if r.status_code != 200:
                return {}
            data = r.content.decode("utf-8")
            response = json.loads(data).get("hitokoto")

            bot.send_group_msg(group_id=group_id, message=response)
        except Exception as e:
            message = f"Error happened: {e}, {traceback.format_exc()}"
            bot.send_group_msg(group_id=group_id, message=message)

    @classmethod
    def proc_history(cls, msg, group_id):

        today = datetime.datetime.today()
        url = "http://api.juheapi.com/japi/toh?v=1.0&month=%s&day=%s&key=776630c7f437ddf719eecbb960a24713" % (
            today.month, today.day
        )
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return {}
            data = r.content.decode("utf-8")
            result = json.loads(data).get("result", []) or []
            if not result:
                return {}

            msg = choice(result).get("des", "") or ""
            bot.send_group_msg(group_id=group_id, message=msg)
        except Exception as e:
            message = f"Error happened: {e}, {traceback.format_exc()}"
            bot.send_group_msg(group_id=group_id, message=message)

    @classmethod
    def proc_sleep(cls, msg, group_id, user_id):
        postfix = msg.replace(" ", "").replace("　", "").split("睡觉")[-1].lower()
        if not postfix or postfix[-1] not in ("s", "m", "h"):
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

    @classmethod
    def proc_whether(cls, msg, group_id):
        if "西雅图" in msg or "seattle" in msg.lower():
            url = "http://www.weather.com.cn/weather/401100101.shtml"
            try:
                r = requests.get(url)
                if r.status_code != 200:
                    return {}
                p = r.content.decode("utf-8")
                start = p.find("今天")
                end = p.find("后天")
                content = p[start: end]
            except Exception:
                content = ""

            today = re.findall("hidden_title\".*value=\"(.*)\"", content)
            if not today:
                return {}
            today = today[0]
            if today:
                bot.send_group_msg(group_id=group_id, message="西雅图天气：" + today)
            return

        city = msg.split("天气")[0].replace("#", "").replace("#", " ")
        url = "http://apis.juhe.cn/simpleWeather/query?key=9228fc70b4ae29bc4f1e0ed6fc57dd04&city=" + city
        try:
            r = requests.get(url)
            if r.status_code != 200:
                return {}

            r = json.loads(r.content.decode("utf-8"))
            result = r.get("result", {})

            realtime = result.get("realtime", {})
            info1 = "%s今日%s, %s%s, %s ℃；" % (
                city,
                realtime.get("info"),
                realtime.get("power"), realtime.get("direct"),
                realtime.get("temperature"),
            )

            future = result.get("future", [{}])[0]
            info2 = "明日%s, %s, %s。" % (
                future.get("weather"), future.get("direct"), future.get("temperature"),
            )
            bot.send_group_msg(group_id=group_id, message=info1 + info2)
        except Exception as e:
            logging.exception("Error when handle weather: %s" % e, exc_info=True)

    @classmethod
    def proc_lucky(cls, msg, group_id):
        constellation = ""
        for c in ("白羊座", "金牛座", "双子座", "巨蟹座",
                  "狮子座", "处女座", "天秤座", "天蝎座",
                  "射手座", "摩羯座", "水瓶座", "双鱼座"):
            if c in msg:
                constellation = c
                break
        if not constellation:
            bot.send_group_msg(group_id=group_id, message="请输入正确的星座， 比如 #狮子座今日运势")

        try:
            url = (
                      "http://web.juhe.cn:8080/constellation/getAll"
                      "?consName=%s"
                      "&type=today&key=5dcf5e7412cb140c57421a54445de177"
                  ) % constellation
            r = requests.get(url)
            if r.status_code != 200:
                return {}

            result = json.loads(r.content.decode("utf-8")).get("summary")

        except Exception as e:
            message = f"Error happened: {e}, {traceback.format_exc()}"
            bot.send_group_msg(group_id=group_id, message=message)
            return

        bot.send_group_msg(group_id=group_id, message="%s: %s" % (constellation, result))

    @classmethod
    def proc_song(cls, msg, group_id):
        song_name = msg.split("点歌")[-1].strip()
        if not song_name:
            return {}

        strip_name = song_name.replace("管珩心", "").replace("泡泡", "").lower().replace("hansy", "").strip()
        song_name = strip_name if strip_name else song_name

        try:
            song_id = BotUtils.get_song_id(song_name)
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Error happened in BotUtils.get_song_id: {e}\n{tb}"
            logging.error(error_msg)
            bot.send_group_msg(group_id=group_id, message=error_msg)
            return

        message = f"[CQ:music,type=163,id={song_id}]" if song_id else f"未找到歌曲「{song_name}」"
        bot.send_group_msg(group_id=group_id, message=message)

    @classmethod
    def proc_help(cls, msg, group_id):
        message = (
            "珩心初号机支持的指令：\n\n"
            f"1.#睡觉10h\n\t(你将被禁言10小时。私聊初号机发送 起床 + 群号即可解除禁言，如``起床{group_id}``。)\n"
            "2.#点歌 北上 管珩心\n"
            "3.#一言\n"
            "4.#北京天气\n"
            "5.#狮子座运势\n"
            "6.#历史上的今天"
        )
        return bot.send_group_msg(group_id=group_id, message=message)


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

        logging.info(
            "Group message received: group_%s [%s][%s](%s qq: %s) -> %s"
            % (group_id, title, card, user_nickname, user_id, msg)
        )

        msg = msg.replace("＃", "#")
        if msg.startswith("#"):

            if msg == "#一言":
                return BotUtils.proc_one_sentence(msg, group_id)

            if msg == "#历史上的今天":
                return BotUtils.proc_history(msg, group_id)

            elif msg.startswith("#睡觉"):
                return BotUtils.proc_sleep(msg, group_id, user_id)

            elif msg.endswith("天气"):
                return BotUtils.proc_whether(msg, group_id)

            elif msg.endswith("运势"):
                return BotUtils.proc_lucky(msg, group_id)

            elif msg.startswith("#点歌"):
                return BotUtils.proc_song(msg, group_id)

            elif msg.startswith("#翻译"):
                return BotUtils.proc_translation(msg, group_id)

            elif msg.strip() in ("#help", "#h", "#帮助", "#指令"):
                return BotUtils.proc_help(msg, group_id)

    elif context["message_type"] == "private":
        user_id = context["sender"]["user_id"]
        user_nickname = context["sender"]["nickname"]
        msg = context["raw_message"]
        logging.info("Private message received: %s(qq: %s) -> %s" % (user_nickname, user_id, msg))

        if user_id == 80873436:
            if msg.startswith("r"):
                msg = msg[1:]
                relay_user_id, raw_msg = msg.split("-", 1)
                try:
                    r = bot.send_private_msg(user_id=int(relay_user_id), message=raw_msg)
                except Exception as e:
                    r = f"E: {e}"
                bot.send_private_msg(user_id=80873436, message=f"Result: {r}")

            elif msg.startswith("add") or msg.startswith("del"):
                uid = int(msg[3:])
                if not uid > 0:
                    bot.send_private_msg(user_id=80873436, message=f"Error uid! {uid}")

                if msg.startswith("add"):
                    message = CookieOperator.add_uid_to_white_list(uid)
                else:
                    message = CookieOperator.remove_uid_from_white_list(uid)

                bot.send_private_msg(user_id=80873436, message=message)

        elif msg.startswith("起床"):
            try:
                group_id = int(msg[2:])
            except Exception:
                group_id = 0

            if group_id in Settings.NOTICE_GROUP_ID_LIST:
                bot.set_group_ban(group_id=group_id, user_id=user_id, duration=0)
            else:
                bot.send_private_msg(
                    user_id=user_id,
                    message="您输入的口令有误。若要解除禁言，请输入“起床+群号”， 如：“起床436496941”"
                )

        elif msg.lower() in ("#help", "#h", "#帮助"):
            message = (
                "珩心初号机支持的指令：(QQ群内可用)\n\n"
                "1.#睡觉10h\n\t(你将被禁言10小时。私聊初号机发送 起床 + 群号即可解除禁言，如``起床436496941``。)\n"
                "2.#点歌 北上 管珩心\n"
                "3.#一言\n"
                "4.#北京天气\n"
                "5.#狮子座运势\n"
                "6.#历史上的今天"
            )
            bot.send_private_msg(user_id=user_id, message=message)

        elif user_id not in (80873436, 310300788):
            bot.send_private_msg(
                user_id=80873436,
                message=f"来自{user_nickname}(QQ: {user_id}) -> \n{msg}",
                auto_escape=True,
            )

        return {}


@bot.on_notice()
def handle_notice(context):
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
    logging.info("notice: %s" % context)
    now = str(datetime.datetime.now())[:19]

    if context["notice_type"] == 'group_increase':
        group_id = context["group_id"]
        if group_id not in (436496941, 159855203):
            return

        user_id = context["user_id"]
        member = bot.get_group_member_info(group_id=group_id, user_id=user_id)
        nickname = member["nickname"]
        operator_id = context["operator_id"]

        sub_type = context["sub_type"]
        if sub_type == "approve":
            sub_type = "主动加群"
        elif sub_type == "invite":
            sub_type = "管理员邀请"

        info = f"{now} QQ: {nickname}({user_id})通过{sub_type}方式加入到本群，审核者QQ({operator_id})"
        asyncio.run(HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info))

        bot.set_group_card(group_id=group_id, user_id=user_id, card="✿泡泡┊" + nickname)
        message = (
            f"欢迎[CQ:at,qq={user_id}] 进入泡泡小黄鸡养殖场！\n\n"
            "群名片格式：✿泡泡┊ + 你的昵称，初号机已经自动为你修改~ \n\n"
            "进群记得发个言哦，否则有可能会被当机器人清理掉，很可怕的哦~ "
            "从今天开始一起跟泡泡守护小黄鸡呀！叽叽叽~"
        )
        bot.send_group_msg(group_id=group_id, message=message)

    elif context["notice_type"] == 'group_decrease':
        group_id = context["group_id"]
        if group_id not in (436496941, 159855203):
            return

        operator_id = context["operator_id"]
        user_id = context["user_id"]

        sub_type = context["sub_type"]
        if sub_type == "leave":
            sub_type = "主动退群"
        elif sub_type == "kick":
            sub_type = "被管理员移出"
        elif sub_type == "kick_me":
            sub_type = "登录号被踢"

        info = f"{now} QQ: ({user_id})通过{sub_type}方式离开本群，操作者QQ({operator_id})"
        asyncio.run(HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info))

    return {}


@bot.on_request()
def handle_request(context):
    logging.info(f"request context: {context}")

    if context["request_type"] == "friend":
        pass

    elif context["request_type"] == "group":
        user_id = context["user_id"]
        comment = context["comment"]
        group_id = context["group_id"]

        sub_type = context["sub_type"]
        if sub_type == "add":
            sub_type = "主动添加"
        elif sub_type == "invite":
            sub_type = "群内成员邀请"

        logging.info(f"Add group request: user_id: {user_id}, comment: {comment}, group_id: {group_id}")
        if group_id == 591691708:
            return {'approve': True}

        elif group_id in (436496941, 159855203):
            now = str(datetime.datetime.now())[:19]
            user_info = asyncio.run(HansyQQGroupUserInfo.get_info(group_id=group_id, user_id=user_id))

            if user_info:
                info = f"{now} QQ({user_id})通过{sub_type}方式尝试加入本群，初号机未处理。验证信息: {comment}"
                asyncio.run(HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info))

                user_info_str = "\n".join([info] + user_info)
                message = f"发现已退出本群成员的重新加群请求！相关记录如下：\n\n{user_info_str}"
                logging.info(message)

                if len(message) > 200:
                    message = message[:200] + "..."
                bot.send_group_msg(group_id=group_id, message=message)

            else:
                info = f"{now} QQ({user_id})通过{sub_type}方式加入本群，由初号机审核通过。验证信息: {comment}"
                asyncio.run(HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info))
                return {'approve': True}

    return


@bot.on_event()
def handle_event(context):
    logging.info(f"event context: {context}")
    return


@bot.on_meta_event()
def handle_meta_event(context):
    logging.info(f"meta_event context: {context}")
    return


bot.run(host='0.0.0.0', port=60000)
