import re
import os
import time
import json
import uuid
import asyncio
import hashlib
import aiohttp
import datetime
import requests
import traceback
from aiohttp import web
from random import randint
from utils.cq import bot_zy as bot
from config import cloud_function_url
from config.log4 import cqbot_logger as logging
from utils.images import DynamicPicturesProcessor
from utils.dao import redis_cache, BiliToQQBindInfo
from utils.biliapi import BiliApi
from utils.highlevel_api import ReqFreLimitApi
from utils.highlevel_api import DBCookieOperator


QQ_GROUP_STAR_LIGHT = 159855203


class BotUtils:
    def __init__(self):
        self.bot = bot

    def post_word_audio(self, word, group_id):
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
            self.bot.send_group_msg(group_id=group_id, message=error_msg)

        else:
            self.bot.send_group_msg(group_id=group_id, message=f"[CQ:record,file={word}.mp3,magic=false]")

    def proc_translation(self, msg, group_id):
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

            self.bot.send_group_msg(group_id=group_id, message=message)

        except Exception as e:
            logging.exception(f"Error: {e}")
            self.bot.send_group_msg(group_id=group_id, message=f"未找到“{word}”的释义 。")

    @staticmethod
    async def get_song_id(song_name):
        songs = []
        no_salt_songs = []
        try:
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
            req_json = {
                "method": "post",
                "url": "http://music.163.com/api/search/pc",
                "headers": headers,
                "data": {"s": song_name, "type": 1, "limit": 50, "offset": 0},
                "params": {},
                "timeout": 10
            }
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(cloud_function_url, json=req_json) as resp:
                    status_code = resp.status
                    content = await resp.text()

            if status_code == 200:
                r = json.loads(content).get("result", {}).get("songs", []) or []
                if isinstance(r, list):
                    no_salt_songs = r
                    songs.extend(r)

            time.sleep(0.3)
            req_json["data"]["s"] = song_name + " 管珩心"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(cloud_function_url, json=req_json) as resp:
                    status_code = resp.status
                    content = await resp.text()

            if status_code == 200:
                r = json.loads(content).get("result", {}).get("songs", [])
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

    def proc_one_sentence(self, msg, group_id):
        try:
            r = requests.get("https://v1.hitokoto.cn/", timeout=10)
            if r.status_code != 200:
                return {}
            data = r.content.decode("utf-8")
            response = json.loads(data).get("hitokoto")

            self.bot.send_group_msg(group_id=group_id, message=response)
        except Exception as e:
            message = f"Error happened: {e}, {traceback.format_exc()}"
            self.bot.send_group_msg(group_id=group_id, message=message)

    def proc_sleep(self, msg, group_id, user_id):
        postfix = msg.replace(" ", "").replace("　", "").replace("#睡觉", "").strip().lower()

        duration_str = ""
        for s in postfix:
            if s in "0123456789":
                duration_str += s
        try:
            duration = abs(int(duration_str.strip()))
        except (ValueError, TypeError):
            return {}

        if postfix[-1] == "m":
            duration *= 60
        elif postfix[-1] == "h":
            duration *= 3600
        elif postfix[-1] == "d":
            duration *= 3600*24

        if duration <= 0:
            return {}

        self.bot.set_group_ban(group_id=group_id, user_id=user_id, duration=min(duration, 720*3600))

    async def proc_song(self, msg, group_id):
        song_name = msg.split("点歌")[-1].strip()
        if not song_name:
            return {}

        strip_name = song_name.replace("管珩心", "").replace("泡泡", "").lower().replace("hansy", "").strip()
        song_name = strip_name if strip_name else song_name

        try:
            song_id = await BotUtils.get_song_id(song_name)
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Error happened in BotUtils.get_song_id: {e}\n{tb}"
            logging.error(error_msg)
            self.bot.send_group_msg(group_id=group_id, message=error_msg)
            return

        message = f"[CQ:music,type=163,id={song_id}]" if song_id else f"未找到歌曲「{song_name}」"
        self.bot.send_group_msg(group_id=group_id, message=message)

    async def proc_query_raffle(self, msg, group_id):
        raw_uid_or_uname = msg[5:].strip()
        if not raw_uid_or_uname:
            return

        try:
            uid = int(raw_uid_or_uname)
        except (ValueError, TypeError):
            uid = await ReqFreLimitApi.get_uid_by_name(user_name=raw_uid_or_uname)

        raffle_list = await ReqFreLimitApi.get_raffle_record(uid)
        if not raffle_list:
            self.bot.send_group_msg(group_id=group_id, message=f"「{raw_uid_or_uname}」: 七天内没有中奖。")
            return

        count = len(raffle_list)
        latest = raffle_list[0]
        query_user_name = latest[0]
        msg_list = []
        for r in raffle_list:
            name, room_id, gift_name, created_time = r
            interval = (datetime.datetime.now() - created_time).total_seconds()
            if interval < 3600:
                date_time_str = "刚刚"
            elif interval < 3600 * 24:
                date_time_str = f"{int(interval / 3600)}小时前"
            else:
                date_time_str = f"{int(interval / (3600 * 24))}天前"
            msg_list.append(f"{date_time_str}在{room_id}直播间获得{gift_name}")
        message = (
            f"「{query_user_name}」在7天内中奖{count}次，详细如下：\n\n" +
            f"{'-'*20}\n" +
            f"\n{'-'*20}\n".join(msg_list) +
            f"\n{'-' * 20}"
        )
        self.bot.send_group_msg(group_id=group_id, message=message)

    async def proc_query_medal(self, msg, group_id):
        raw_uid_or_uname = msg[5:].strip()
        if not raw_uid_or_uname:
            return

        try:
            uid = int(raw_uid_or_uname)
        except (ValueError, TypeError):
            uid = await ReqFreLimitApi.get_uid_by_name(user_name=raw_uid_or_uname)

        if not uid:
            return

        user_name = await BiliApi.get_user_name(uid=uid)

        flag, r = await BiliApi.get_user_medal_list(uid=uid)
        if not flag or not isinstance(r, list) or not r:
            message = f"未查询到{user_name}(uid: {uid})拥有的勋章。检查用户名或uid是否正确。"
            self.bot.send_group_msg(group_id=group_id, message=message)
            return

        medal_list = sorted(r, key=lambda x: (x["level"], x["intimacy"]), reverse=True)
        msg_list = []
        for m in medal_list:
            name = m["medal_name"]
            level = m["level"]
            current = m["intimacy"]
            total = m["next_intimacy"]
            msg_list.append(f"[{name}] {level}级，{current}/{total}")

        message = "\n".join(msg_list)
        self.bot.send_group_msg(group_id=group_id, message=f"{user_name}(uid: {uid})拥有的勋章如下：\n\n{message}")

    async def proc_lt_status(self, user_id, msg, group_id=None):

        def response(m):
            if group_id:
                self.bot.send_group_msg(group_id=group_id, message=m)
            else:
                self.bot.send_private_msg(user_id=user_id, message=m)

        bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        if not bili_uid:
            if group_id:
                message = f"[CQ:at,qq={user_id}] 你尚未绑定B站账号。请私聊我然后发送\"挂机查询\"以完成绑定。"
                return self.bot.send_group_msg(group_id=group_id, message=message)

            number = randint(1000, 9999)
            key = f"BILI_BIND_CHECK_KEY_{number}"
            await redis_cache.set(key=key, value=user_id, timeout=3600)
            message = f"你尚未绑定B站账号。请你现在去13369254直播间发送以下指令： 绑定{number}"
            self.bot.send_private_msg(user_id=user_id, message=message)
            return

        try:
            postfix = int(msg[5:])
            assert postfix > 0
            bili_uid = postfix
        except (ValueError, TypeError, AssertionError):
            pass

        flag, msg = await DBCookieOperator.get_lt_status(uid=bili_uid)
        response(msg)

    async def proc_query_bag(self, user_id, msg, group_id):
        bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        if not bili_uid:
            message = f"[CQ:at,qq={user_id}] 你尚未绑定B站账号。请私聊我然后发送\"挂机查询\"以完成绑定。"
            self.bot.send_group_msg(group_id=group_id, message=message)
            return True

        try:
            postfix = int(msg[3:])
            assert postfix > 0
            bili_uid = postfix
        except (ValueError, TypeError, AssertionError):
            pass

        user = await DBCookieOperator.get_by_uid(user_id=bili_uid, available=True)
        if not user:
            message = f"未查询到用户「{bili_uid}」。可能用户已过期，请重新登录。"
            self.bot.send_group_msg(group_id=group_id, message=message)
            return

        bag_list = await BiliApi.get_bag_list(user.cookie)
        if not bag_list:
            message = f"{user.name}(uid: {user.uid})的背包里啥都没有。"
            self.bot.send_group_msg(group_id=group_id, message=message)
            return

        result = {}
        for bag in bag_list:
            corner_mark = bag["corner_mark"]
            result.setdefault(corner_mark, {}).setdefault(bag["gift_name"], []).append(bag["gift_num"])

        prompt = []
        for corner_mark, gift_info in result.items():
            gift_prompt = []
            for gift_name, gift_num_list in gift_info.items():
                gift_prompt.append(f"{gift_name}*{sum(gift_num_list)}")
            gift_prompt = "、".join(gift_prompt)
            prompt.append(f"{corner_mark}的{gift_prompt}")

        prompt = ',\n'.join(prompt)
        message = f"{user.name}(uid: {user.uid})的背包里有:\n{prompt}。"
        self.bot.send_group_msg(group_id=group_id, message=message)

    async def proc_dynamic(self, user_id, msg, group_id=None):
        def response(m):
            if group_id is not None:
                self.bot.send_group_msg(group_id=group_id, message=m)
            else:
                self.bot.send_private_msg(user_id=user_id, message=m)

        try:
            user_name_or_dynamic_id = msg[3:].strip()
            if not user_name_or_dynamic_id.isdigit():
                bili_uid = await ReqFreLimitApi.get_uid_by_name(user_name_or_dynamic_id)
                if bili_uid is None:
                    response(f"未能搜索到该用户：{user_name_or_dynamic_id}。")
                    return

                flag, dynamics = await BiliApi.get_user_dynamics(uid=bili_uid)
                if not flag or not dynamics:
                    raise ValueError("Fetch dynamics Failed!")
                dynamic_id = dynamics[0]["desc"]["dynamic_id"]

            elif len(user_name_or_dynamic_id) < 14:
                flag, dynamics = await BiliApi.get_user_dynamics(uid=int(user_name_or_dynamic_id))
                if not flag:
                    raise ValueError("Fetch dynamics Failed!")

                if not dynamics:
                    response(f"该用户未发布B站动态。")
                    return

                dynamic_id = dynamics[0]["desc"]["dynamic_id"]

            else:
                dynamic_id = int(user_name_or_dynamic_id)

        except (TypeError, ValueError, IndexError):
            response(f"错误的指令，示例：\"#动态 偷闲一天打个盹\"或 \"#动态 278441699009266266\" 或 \"#动态 20932326\".")
            return

        flag, dynamic = await BiliApi.get_dynamic_detail(dynamic_id=dynamic_id)
        if not flag:
            response(f"未能获取到动态：{dynamic_id}.")
            return

        master_name = dynamic["desc"]["user_profile"]["info"]["uname"]
        master_uid = dynamic["desc"]["user_profile"]["info"]["uid"]
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(dynamic["desc"]["timestamp"]))
        prefix = f"{master_name}(uid: {master_uid})最新动态({timestamp})：\n\n"

        content, pictures = await BiliApi.get_user_dynamic_content_and_pictures(dynamic)
        if not pictures:
            message = prefix + "\n".join(content)
            response(message)
            return

        work_path = f"/tmp/bili_dynamic_{int(time.time())}"
        if not os.path.exists(work_path):
            os.mkdir(work_path)

        index = 0
        last_pic_name = None
        for pic in pictures:
            ex_name = pic.split(".")[-1]
            last_pic_name = f"{index}.{ex_name}"
            cmd = f"wget -O {work_path}/{last_pic_name} \"{pic}\""
            os.system(cmd)
            index += 1

        if index > 1:
            p = DynamicPicturesProcessor(path=work_path)
            flag, file_name = p.join()
        else:
            flag = True
            file_name = f"b_{int(time.time()*1000):0x}." + last_pic_name.split(".")[-1]
            os.system(f"mv {work_path}/{last_pic_name} /home/ubuntu/coolq_zy/data/image/{file_name}")

        if flag:
            message = prefix + "\n".join(content)
            message = f"{message}\n [CQ:image,file={file_name}]"
        else:
            message = prefix + "\n".join(content) + "\n" + "\n".join(pictures)
        response(message)

    async def proc_query_guard(self, user_id, msg, group_id=None):
        def response(m):
            if group_id is not None:
                self.bot.send_group_msg(group_id=group_id, message=m)
            else:
                self.bot.send_private_msg(user_id=user_id, message=m)

        user_name_or_uid = msg[4:].strip()
        if not user_name_or_uid:
            bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        else:
            if user_name_or_uid.isdigit():
                bili_uid = int(user_name_or_uid)
            else:
                bili_uid = await ReqFreLimitApi.get_uid_by_name(user_name_or_uid)

        if not bili_uid:
            return response(f"指令错误，不能查询到用户: {user_name_or_uid}")

        if group_id:
            # 频率检查
            key = f"LT_QUERY_GUARD_REQ_FRQ_CONTROL_{group_id}"
            key2 = f"LT_QUERY_GUARD_REQ_FRQ_CONTROL_PROMPT_{group_id}"

            value = await redis_cache.get(key=key)
            if value is None:
                await redis_cache.set(key=key, value=1, timeout=60)
                await redis_cache.delete(key=key2)
                pass

            else:
                has_prompted = await redis_cache.get(key=key2)
                if not has_prompted:
                    response(f"为防刷屏，请私聊发送指令(一分钟内本提示不再发出): \n{msg}")
                    await redis_cache.set(key=key2, value=1, timeout=50)
                return

        data = await ReqFreLimitApi.get_guard_record(uid=int(bili_uid))
        return response(data)


class BotHandler:
    NOTICE_GROUP_ID_LIST = [
        159855203,  # test
        883237694,  # guard
        436496941,
        591691708,  # 禁言群
    ]

    @classmethod
    async def handle_group_message(cls, context):
        sender = context["sender"]
        user_id = sender["user_id"]
        user_nickname = sender["nickname"]
        title = sender.get("title", "--")
        card = sender.get("card", "--")
        group_id = context["group_id"]
        msg = context["raw_message"]

        logging.info(
            "Group message received: group_%s [%s][%s](%s qq: %s) -> %s"
            % (group_id, title, card, user_nickname, user_id, msg)
        )

        msg = msg.replace("＃", "#")
        if msg == "一言":
            msg = "#一言"
        elif msg == "挂机查询":
            msg = "#挂机查询"
        elif msg == "背包":
            msg = "#背包"

        if not msg.startswith("#"):
            return

        p = BotUtils()

        if msg.startswith("#一言"):
            return p.proc_one_sentence(msg, group_id)

        elif msg.startswith("#点歌"):
            return await p.proc_song(msg, group_id)

        elif msg.startswith("#翻译"):
            return p.proc_translation(msg, group_id)

        elif msg.startswith("#中奖查询"):
            return await p.proc_query_raffle(msg, group_id)

        elif msg.startswith("#勋章查询"):
            return await p.proc_query_medal(msg, group_id)

        elif msg.startswith("#大航海"):
            return await p.proc_query_guard(user_id, msg=msg, group_id=group_id)

        elif msg.startswith("#动态"):
            return await p.proc_dynamic(user_id, msg=msg, group_id=group_id)

        # -------- 以下限制本群访问 ---------
        if group_id != QQ_GROUP_STAR_LIGHT:
            return

        if msg.startswith("#挂机查询"):
            return await p.proc_lt_status(user_id, msg=msg, group_id=group_id)

        elif msg.startswith("#背包"):
            return await p.proc_query_bag(user_id, msg=msg, group_id=group_id)

    @classmethod
    async def handle_private_message(cls, context):
        user_id = context["sender"]["user_id"]
        user_nickname = context["sender"]["nickname"]
        msg = context["raw_message"]
        p = BotUtils()

        if msg.startswith("挂机查询"):
            return await p.proc_lt_status(user_id, msg=f"#{msg}")

        elif msg.startswith("#动态"):
            return await p.proc_dynamic(user_id, msg=msg)

        elif msg.startswith("#雨声雷鸣动态-"):
            dynamic_id = int(msg.split("-")[-1])
            msg = f"#动态{dynamic_id}"
            return await p.proc_dynamic(user_id, msg=msg, group_id=895699676)

        elif msg.startswith("#大航海"):
            return await p.proc_query_guard(user_id, msg=msg)

    @classmethod
    async def handle_message(cls, context):
        if context["message_type"] == "group":
            return await cls.handle_group_message(context)

        elif context["message_type"] == "private":
            return await cls.handle_private_message(context)

    @classmethod
    async def handle_request(cls, context):
        if context["request_type"] == "group":
            return
        else:
            return {'approve': True}


async def handler(request):
    context = await request.json()

    if context["post_type"] == "message":
        response = await BotHandler.handle_message(context)
    elif context["post_type"] == "request":
        response = await BotHandler.handle_request(context)
    else:
        response = None

    if isinstance(response, dict) and response:
        return web.Response(text=json.dumps(response), content_type="application/json")
    else:
        return web.Response(text="", status=204)
