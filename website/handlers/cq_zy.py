import re
import os
import time
import json
import uuid
import random
import asyncio
import hashlib
import aiohttp
import datetime
import requests
import traceback
from config import g
from aiohttp import web
from random import randint
from utils.cq import async_zy
from utils.biliapi import BiliApi
from utils.cq import bot_zy as bot
from config import cloud_function_url
from utils.db_raw_query import AsyncMySQL
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import cqbot_logger as logging
from utils.highlevel_api import DBCookieOperator
from utils.images import DynamicPicturesProcessor
from utils.dao import (
    RedisLock,
    redis_cache,
    LTTempBlack,
    BiliToQQBindInfo,
    DelayAcceptGiftsMQ,
    SuperDxjUserAccounts,
)


class BotUtils:
    def __init__(self, user_id=None, group_id=None):
        self.bot = bot
        self.user_id = user_id
        self.group_id = group_id

    def response(self, msg):
        if self.group_id is not None:
            self.bot.send_group_msg(group_id=self.group_id, message=msg)
        else:
            self.bot.send_private_msg(user_id=self.user_id, message=msg)

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

    async def proc_query_raffle(self, msg, user_id, group_id=None):
        self.user_id = user_id
        self.group_id = group_id

        raw_uid_or_uname = msg[5:].strip()
        if not raw_uid_or_uname:
            raw_uid_or_uname = await BiliToQQBindInfo.get_by_qq(qq=user_id)

        if not raw_uid_or_uname:
            self.response(f"请绑定你的B站账号，或者在指令后加上正确的B站用户id。")
            return

        try:
            uid = int(raw_uid_or_uname)
        except (ValueError, TypeError):
            uid = await ReqFreLimitApi.get_uid_by_name(user_name=raw_uid_or_uname)

        raffle_list = await ReqFreLimitApi.get_raffle_record(uid)
        if not raffle_list:
            self.response(f"{raw_uid_or_uname}: 七天内没有中奖。")
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
        self.response(message)

    async def proc_query_medal(self, msg, user_id, group_id=None):
        self.user_id = user_id
        self.group_id = group_id

        raw_uid_or_uname = msg[5:].strip()
        if not raw_uid_or_uname:
            raw_uid_or_uname = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        if not raw_uid_or_uname:
            self.response(f"请输入正确的用户名。")
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
            self.response(message)
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
        self.response(f"{user_name}(uid: {uid})拥有的勋章如下：\n\n{message}")

    async def proc_lt_status(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        bili_uid_list = await BiliToQQBindInfo.get_all_bili(qq=user_id)
        if not bili_uid_list:
            message = f"你尚未绑定B站账号。请私聊我然后发送\"#绑定\"以完成绑定。"
            self.response(message)
            return

        bili_uid_str = msg[5:]
        if bili_uid_str:
            try:
                assigned_uid = int(bili_uid_str)
            except (TypeError, ValueError):
                self.response("指令错误，拒绝服务。")
                return

            if assigned_uid not in bili_uid_list:
                self.response("未找到此用户。")
                return

        else:
            assigned_uid = bili_uid_list[0]

        flag, msg = await DBCookieOperator.get_lt_status(uid=assigned_uid)
        self.response(msg)

    async def proc_record_followings(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        if not bili_uid:
            self.response(f"你尚未绑定B站账号，请私聊我然后发送\"#绑定\"进行绑定。")
            return

        flag, fs = await BiliApi.get_followings(user_id=bili_uid)
        if not flag:
            self.response(f"记录失败！{fs}")
            return
        key = f"LT_FOLLOWINGS_{bili_uid}"
        await redis_cache.set(key, fs, timeout=3600*24*30)
        self.response(f"操作成功！记录下了你最新关注的{len(fs)}个up主。")

    async def proc_unfollow(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        if not bili_uid:
            self.response(f"你尚未绑定B站账号，请私聊我然后发送“#绑定”进行绑定。")
            return

        cookie_obj = await DBCookieOperator.get_by_uid(user_id=bili_uid, available=True)
        if not cookie_obj:
            self.response("你的登录已过期！请登录辣条宝藏站点重新登录。")
            return

        async with RedisLock(key=f"LT_UNFOLLOW_{user_id}") as _:
            key = f"LT_FOLLOWINGS_{bili_uid}"
            follows = await redis_cache.get(key)
            if not isinstance(follows, (list, set)):
                self.response("你没有记录你的关注列表，不能操作。")
                return

            flag, current_follows = await BiliApi.get_followings(user_id=bili_uid)
            if not flag:
                self.response(f"操作失败，未能获取你的关注列表: {current_follows}")
                return

            need_delete = list(set(current_follows) - set(follows))
            if need_delete:
                self.response(f"开始操作，需要取关{len(need_delete)}个up主。可能会耗费较久的时间，期间不要重复发送指令。")

            for i, uid in enumerate(need_delete):
                flag, msg = await BiliApi.unfollow(user_id=uid, cookie=cookie_obj.cookie)
                if not flag:
                    self.response(f"在处理第{i}个时发生了错误：{msg}.")
                    return
                await asyncio.sleep(0.2)
            self.response(f"操作成功！取关了{len(need_delete)}个up主。")

    async def proc_query_bag(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        if not bili_uid:
            message = f"你尚未绑定B站账号。请私聊我然后发送\"#绑定\"以完成绑定。"
            self.response(message)
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
            self.response(message)
            return

        bag_list = await BiliApi.get_bag_list(user.cookie)
        if not bag_list:
            message = f"{user.name}(uid: {user.uid})的背包里啥都没有。"
            self.response(message)
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
        self.response(message)

    async def proc_dynamic(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        try:
            user_name_or_dynamic_id = msg[3:].strip()
            if not user_name_or_dynamic_id:
                self.response(f"请输入正确的用户名。")
                return

            if not user_name_or_dynamic_id.isdigit():
                bili_uid = await ReqFreLimitApi.get_uid_by_name(user_name_or_dynamic_id)
                if bili_uid is None:
                    self.response(f"未能搜索到该用户：{user_name_or_dynamic_id}。")
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
                    self.response(f"该用户未发布B站动态。")
                    return

                dynamic_id = dynamics[0]["desc"]["dynamic_id"]

            else:
                dynamic_id = int(user_name_or_dynamic_id)

        except (TypeError, ValueError, IndexError):
            self.response(f"错误的指令，示例：\"#动态 偷闲一天打个盹\"或 \"#动态 278441699009266266\" 或 \"#动态 20932326\".")
            return

        flag, dynamic = await BiliApi.get_dynamic_detail(dynamic_id=dynamic_id)
        if not flag:
            self.response(f"未能获取到动态：{dynamic_id}.")
            return

        master_name = dynamic["desc"]["user_profile"]["info"]["uname"]
        master_uid = dynamic["desc"]["user_profile"]["info"]["uid"]
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(dynamic["desc"]["timestamp"]))
        prefix = f"{master_name}(uid: {master_uid})最新动态({timestamp})：\n\n"

        content, pictures = await BiliApi.get_user_dynamic_content_and_pictures(dynamic)
        if not pictures:
            message = prefix + "\n".join(content)
            self.response(message)
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
        self.response(message)

    async def proc_query_guard(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        user_name_or_uid = msg[4:].strip()
        if not user_name_or_uid:
            bili_uid = await BiliToQQBindInfo.get_by_qq(qq=user_id)
        else:
            if user_name_or_uid.isdigit():
                bili_uid = int(user_name_or_uid)
            else:
                bili_uid = await ReqFreLimitApi.get_uid_by_name(user_name_or_uid)

        if not bili_uid:
            self.response(f"指令错误，不能查询到用户: {user_name_or_uid}")
            return

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
                    self.response(f"为防刷屏，请私聊发送指令(一分钟内本提示不再发出): \n{msg}")
                    await redis_cache.set(key=key2, value=1, timeout=50)
                return

        data = await ReqFreLimitApi.get_guard_record(uid=int(bili_uid))
        self.response(data)
        return

    async def proc_bind(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        message = ""
        bili_uid_list = await BiliToQQBindInfo.get_all_bili(qq=user_id)

        if len(bili_uid_list) > 0:
            message += f"你已经绑定到Bili用户:\n{'、'.join([str(_) for _ in bili_uid_list])}。绑定更多账号请按如下操作：\n"

        code = f"{randint(0x1000, 0xffff):0x}"
        key = f"BILI_BIND_CHECK_KEY_{code}"
        if await redis_cache.set_if_not_exists(key=key, value=user_id, timeout=3600):
            message += f"请你现在去1234567直播间发送以下指令:\nhttps://live.bilibili.com/1234567\n\n你好{code}"
        else:
            message += f"操作失败！系统繁忙，请5秒后再试。"
        self.response(message)
        return

    async def proc_unbind(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        message = f"要想解绑，请你现在去1234567直播间发送:\n\n再见"
        self.response(message)

    async def proc_chicken(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        if user_id != g.QQ_NUMBER_DD:
            if not await redis_cache.set_if_not_exists(f"LT_PROC_CHICKEN_{user_id}", 1, timeout=180):
                ttl = await redis_cache.ttl(f"LT_PROC_CHICKEN_{user_id}")
                self.response(f"请{ttl}秒后再发送此命令。")
                return

        last_active_time = await redis_cache.get("LT_LAST_ACTIVE_TIME")
        if not isinstance(last_active_time, int):
            last_active_time = 0
        i = int(time.time()) - last_active_time

        def gen_time_prompt(interval):
            if interval > 3600 * 24 * 365:
                return f"很久以前"
            elif interval > 3600 * 24:
                return f"约{int(interval // (3600 * 24))}天前"
            elif interval > 3600:
                return f"约{int(interval // 3600)}小时前"
            elif interval > 60:
                return f"约{int(interval // 60)}分钟前"
            return f"{int(interval)}秒前"

        all_gifts = await DelayAcceptGiftsMQ.get_all()
        gifts = []
        score = []
        for i, gift in enumerate(all_gifts):
            if i % 2 == 0:
                gifts.append(gift)
            else:
                score.append(gift)

        message = f"辣🐔最后活跃时间: {gen_time_prompt(i)}，队列中有{len(gifts)}个未收大宝贝：\n\n{'-'*20}\n"

        room_id_q = await AsyncMySQL.execute(
            "select real_room_id, short_room_id from biliuser where real_room_id in %s;",
            ({int(d.split("$")[1]) for d in gifts},)
        )
        room_id_map = {r[0]: r[1] for r in room_id_q if r[1]}
        g_names_map = {}
        prompt_gift_list = []
        for i, gift in enumerate(gifts):
            key_type, room_id, raffle_id, *args = gift.split("$")
            room_id = int(room_id)
            room_id = room_id_map.get(room_id, room_id)
            accept_time = -1 * int(time.time() - score[i])
            if accept_time < 0:
                accept_time = 0

            if key_type == "T":
                gift_type = args[0]
                if gift_type in g_names_map:
                    gift_name = g_names_map[gift_type]
                else:
                    gift_name = await redis_cache.get(key=f"GIFT_TYPE_{gift_type}")
                    g_names_map[gift_type] = gift_name
                prompt_gift_list.append((gift_name, room_id, accept_time))
            elif key_type == "G":
                privilege_type = args[0]
                if privilege_type == "1":
                    gift_name = "总督"
                elif privilege_type == "2":
                    gift_name = "提督"
                else:
                    gift_name = "舰长"
                prompt_gift_list.append((gift_name, room_id, accept_time))
        prompt_gift_list.sort(key=lambda x: (x[0], x[2], x[1]))
        prompt = []
        for p in prompt_gift_list:
            minutes = p[2] // 60
            seconds = p[2] % 60
            time_prompt = f"{seconds}秒"
            if minutes > 0:
                time_prompt = f"{minutes}分" + time_prompt

            prompt.append(f"{p[0]}: {p[1]}, {time_prompt}后领取")
        message += "；\n".join(prompt)
        self.response(message)

    async def proc_unfreeze(self, msg, user_id, group_id=None):
        self.group_id = group_id
        self.user_id = user_id

        try:
            bili_uid = int(msg[2:].strip())
        except (IndexError, ValueError, TypeError):
            self.response("指令错误。请发送“解冻”+B站uid， 如:\n解冻731556")
            return

        bili_uids = await BiliToQQBindInfo.get_all_bili(qq=user_id)
        if bili_uid not in bili_uids:
            self.response("UID错误。")
            return

        if bili_uid not in await LTTempBlack.get_blocked():
            self.response(f"你（uid: {bili_uid}）没有被冻。此命令会加重辣🐔的工作负担，请不要频繁发送。\n\n爱护辣🐔，人人有责。")
            return

        await LTTempBlack.remove(uid=bili_uid)
        self.response("操作成功。")

    async def proc_help(self, msg, user_id, group_id):
        self.group_id = group_id
        self.user_id = user_id
        if group_id:
            message = (
                "所有指令必须以`#`号开始。公屏指令：\n"
                "1.#一言\n"
                "2.#点歌\n"
                "3.#翻译\n"
                "4.#动态\n\n"
                "私聊指令请私聊我然后发送#h。"
            )
        else:
            message = (
                "私聊指令如下：（可以使用前面的数字序号代替）\n"
                "1.#背包\n"
                "2.#动态\n"
                "3.#大航海\n"
                "4.#中奖查询\n"
                "5.#勋章查询\n"
                "6.#挂机查询\n"
                "7.#绑定\n"
                "8.#解绑"
            )
            if user_id == g.QQ_NUMBER_DD:
                message += (
                    f"\n"
                    f"ac、dc: 辣条白名单\n"
                    f"as、ds: 超级答谢鸡\n"
                    f"++123+1212、--33234: 绑定解绑\n"
                    f"approve、11、33、44、g、r"
                )
        self.response(message)


class BotHandler:

    @classmethod
    async def handle_group_message(cls, context):
        sender = context["sender"]
        user_id = sender["user_id"]
        user_nickname = sender["nickname"]
        title = sender.get("title", "--")
        card = sender.get("card", "--")
        group_id = context["group_id"]
        msg = context["message"]
        logging.info(f"群消息: ({group_id}) [{title}][{card}]{user_nickname}({user_id}) -> {msg}")

        msg = msg.replace("＃", "#")
        p = BotUtils()
        if msg in ("一言", "#一言"):
            return p.proc_one_sentence(msg, group_id)

        elif msg.startswith("#点歌"):
            return await p.proc_song(msg, group_id)

        elif msg.startswith("#翻译"):
            return p.proc_translation(msg, group_id)

        elif msg.startswith("#动态"):
            return await p.proc_dynamic(msg, user_id, group_id=group_id)

        elif msg.lower() in ("#h", "#help", "#帮助", "#指令"):
            return await p.proc_help(msg, user_id, group_id=group_id)

    @classmethod
    async def handle_private_message(cls, context):
        user_id = context["sender"]["user_id"]
        user_nickname = context["sender"]["nickname"]
        msg = context["raw_message"]

        if user_id == g.QQ_NUMBER_DD:
            if msg.startswith("approve"):
                flag = msg[7:]
                r = await async_zy.set_friend_add_request(flag=flag, approve=True)
                await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=f"已通过：{r}")
                return

            elif msg.startswith("ac"):
                account = msg[2:]
                cookie_obj = await DBCookieOperator.add_uid_or_account_to_white_list(account=account)
                bot.send_private_msg(
                    user_id=80873436,
                    message=f"白名单已添加: {account}, id: {cookie_obj.id}"
                )
                return

            elif msg.startswith("dc"):
                account = msg[2:]
                r = await DBCookieOperator.del_uid_or_account_from_white_list(account=account)
                bot.send_private_msg(user_id=80873436, message=f"白名单已删除: {account}, id: {r}")
                return

            elif msg.startswith("44"):
                message = msg[2:]
                dd_obj = await DBCookieOperator.get_by_uid("DD")
                await BiliApi.send_danmaku(
                    message=message,
                    room_id=2516117,
                    cookie=dd_obj.cookie
                )
                return

            elif msg.startswith("11"):
                message = msg[2:]
                dd_obj = await DBCookieOperator.get_by_uid("LP")
                await BiliApi.send_danmaku(
                    message=message,
                    room_id=2516117,
                    cookie=dd_obj.cookie
                )
                return

            elif msg.startswith("33"):
                message = msg[2:]
                dd_obj = await DBCookieOperator.get_by_uid("DD")
                await BiliApi.send_danmaku(
                    message=message,
                    room_id=13369254,
                    cookie=dd_obj.cookie
                )
                return

            elif msg.startswith("as"):
                live_room_id = int(msg[2:])
                real_room_id = await BiliApi.force_get_real_room_id(room_id=live_room_id)
                await SuperDxjUserAccounts.set(user_id=real_room_id, password="123456")

                restart_info = os.popen("/usr/local/bin/supervisorctl restart dxj_super").read()
                message = f"添加完成: {live_room_id} -> {real_room_id}. restart_info: \n{restart_info}"
                bot.send_private_msg(user_id=80873436, message=message)
                return

            elif msg.startswith("ds"):
                live_room_id = int(msg[2:])
                real_room_id = await BiliApi.force_get_real_room_id(room_id=live_room_id)
                await SuperDxjUserAccounts.delete(user_id=real_room_id)
                restart_info = os.popen("/usr/local/bin/supervisorctl restart dxj_super").read()
                message = f"删除完成: {live_room_id} -> {real_room_id}. restart_info:\n{restart_info}"
                bot.send_private_msg(user_id=80873436, message=message)
                return

            elif msg.startswith("++"):
                qq, bili = [int(_) for _ in msg[2:].split("+")]
                r = await BiliToQQBindInfo.bind(qq=qq, bili=bili)
                all_bili = await BiliToQQBindInfo.get_all_bili(qq=qq)
                message = f"绑定结果: {r}。{qq} -> {'、'.join([str(b) for b in all_bili])}"
                await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)
                return

            elif msg.startswith("--"):
                bili = int(msg[2:])
                qq = await BiliToQQBindInfo.unbind(bili=bili)
                if qq:
                    all_bili = await BiliToQQBindInfo.get_all_bili(qq=qq)
                else:
                    all_bili = []
                message = f"解绑。{qq} -> {'、'.join([str(b) for b in all_bili])}"
                await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)
                return

            elif msg.startswith("g"):
                group_number, message = msg[1:].split("g", 1)
                if group_number == "#":
                    group_id = g.QQ_GROUP_井
                else:
                    group_id = int(group_number)
                await async_zy.send_group_msg(group_id=group_id, message=message)
                return

            elif msg.startswith("r"):
                qq_number, message = msg[1:].split("r", 1)
                qq_number = int(qq_number)
                await async_zy.send_private_msg(user_id=qq_number, message=message)
                return

        for short, full in [
            ("1", "#背包"),
            ("2", "#动态"),
            ("3", "#大航海"),
            ("4", "#中奖查询"),
            ("5", "#勋章查询"),
            ("6", "#挂机查询"),
            ("7", "#绑定"),
            ("8", "#解绑"),
        ]:
            if msg.startswith(short):
                msg = msg.replace(short, full, 1)
                break

        p = BotUtils()
        if msg.startswith("#背包"):
            return await p.proc_query_bag(msg, user_id, group_id=None)

        elif msg.startswith("#动态"):
            return await p.proc_dynamic(msg, user_id, group_id=None)

        elif msg.startswith("#大航海"):
            return await p.proc_query_guard(msg, user_id, group_id=None)

        elif msg.startswith("#中奖查询"):
            return await p.proc_query_raffle(msg, user_id, group_id=None)

        elif msg.startswith("#勋章查询"):
            return await p.proc_query_medal(msg, user_id, group_id=None)

        elif msg.startswith("#挂机查询"):
            return await p.proc_lt_status(msg, user_id, group_id=None)

        elif msg.startswith("#绑定"):
            return await p.proc_bind(msg, user_id, group_id=None)

        elif msg.startswith("#解绑"):
            return await p.proc_unbind(msg, user_id, group_id=None)

        elif msg.lower() in ("#h", "#help", "#帮助", "#指令"):
            return await p.proc_help(msg, user_id, group_id=None)

        elif msg == "lt":
            token = f"{random.randint(0x100000000000, 0xFFFFFFFFFFFF):0x}"
            key = F"LT_ACCESS_TOKEN_{token}"
            await redis_cache.incr(key=key)
            await redis_cache.expire(key=key, timeout=180)
            message = f"宝藏站点地址: （如果出现503错误请多刷新几次）\n\nhttps://www.madliar.com/lt_{token}"
            logging.info(F"LT_ACCESS_TOKEN_GEND: {token}, user_id: {user_id}")
            await async_zy.send_private_msg(user_id=user_id, message=message)
            return

        elif msg in ("鸡", "🐔"):
            return await p.proc_chicken(msg, user_id)

        elif msg.startswith("解冻"):
            return await p.proc_unfreeze(msg, user_id)

    @classmethod
    async def handle_message(cls, context):
        if context["message_type"] == "group":
            return await cls.handle_group_message(context)

        elif context["message_type"] == "private":
            return await cls.handle_private_message(context)

    @classmethod
    async def handle_request(cls, context):
        # if context["request_type"] == "group":
        #     return
        try:
            flag, data = await async_zy.get_stranger_info(user_id=context['user_id'], no_cache=True)
            if not flag:
                data = {}
        except Exception as e:
            message = (
                f"Error happened in handle_request -> get_stranger_info. "
                f"e: {e}. "
                f"context: {context}\b{traceback.format_exc()}"
            )
            await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)
            data = {}

        age = data.get("age", "-")
        nickname = data.get("nickname", "-")
        sex = data.get("sex", "-")

        message = (
            f"梓亚收到好友请求:\n"
            f"验证消息: {context['comment']}\n"
            f"{nickname}({context['user_id']}) - {sex}\n"
            f"年龄: {age}\n\n"
            f"approve{context['flag']}"
        )
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)


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
