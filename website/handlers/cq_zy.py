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
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import cqbot_logger as logging
from utils.reconstruction_model import LTUserCookie
from utils.reconstruction_model import LTUserCookie
from utils.images import DynamicPicturesProcessor
from utils.dao import (
    RedisLock,
    redis_cache,
    LTTempBlack,
    BiliToQQBindInfo,
    DelayAcceptGiftsQueue,
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

    def proc_translation(self, msg):
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
            return message

        except Exception as e:
            logging.exception(f"Error: {e}")
            return f"未找到“{word}”的释义 。"

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

    async def proc_one_sentence(self):

        async def get_one_sentence():
            async with aiohttp.request("get", "https://v1.hitokoto.cn/") as req:
                if req.status != 200:
                    return ""
                r = await req.json()
                return r.get("hitokoto") or ""

        key = f"LT_ONE_SENTENCE_{self.group_id}"
        if not await redis_cache.set_if_not_exists(key=key, value="1", timeout=300):
            if await redis_cache.set_if_not_exists(key=f"{key}_FLUSH", value="1", timeout=300):
                s = await get_one_sentence()
                return f"{s}\n(防刷屏，5分钟内不再响应)"
            return

        return await get_one_sentence()

    async def proc_song(self, msg):
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
            return error_msg

        return f"[CQ:music,type=163,id={song_id}]" if song_id else f"未找到歌曲「{song_name}」"

    async def proc_query_raffle(self, msg):
        raw_uid_or_uname = msg[5:].strip()
        if not raw_uid_or_uname:
            raw_uid_or_uname = await BiliToQQBindInfo.get_by_qq(qq=self.user_id)

        if not raw_uid_or_uname:
            return f"请绑定你的B站账号，或者在指令后加上正确的B站用户id。"

        try:
            uid = int(raw_uid_or_uname)
        except (ValueError, TypeError):
            uid = await ReqFreLimitApi.get_uid_by_name(user_name=raw_uid_or_uname)

        raffle_list = await ReqFreLimitApi.get_raffle_record(uid)
        if not raffle_list:
            return f"{raw_uid_or_uname}: 七天内没有中奖。"

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
            f"{query_user_name}(uid: {uid})在7天内中奖{count}次，详细如下：\n\n" +
            f"{'-'*20}\n" +
            f"\n{'-'*20}\n".join(msg_list) +
            f"\n{'-' * 20}"
        )
        return message

    async def proc_lt_status(self, msg):
        bili_uid_list = await BiliToQQBindInfo.get_all_bili(qq=self.user_id)
        if not bili_uid_list:
            return f"你尚未绑定B站账号。请私聊我然后发送\"#绑定\"以完成绑定。"

        bili_uid_str = msg[5:]
        if bili_uid_str:
            try:
                assigned_uid = int(bili_uid_str)
            except (TypeError, ValueError):
                return "指令错误，拒绝服务。"

            if self.user_id != g.QQ_NUMBER_DD and assigned_uid not in bili_uid_list:
                return "未找到此用户。"

        else:
            assigned_uid = bili_uid_list[0]

        flag, msg = await LTUserCookie.get_lt_status(uid=assigned_uid)
        return msg

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

        cookie_obj = await LTUserCookie.get_by_uid(user_id=bili_uid, available=True)
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

    async def proc_query_bag(self, msg):
        bili_uid = await BiliToQQBindInfo.get_by_qq(qq=self.user_id)
        if not bili_uid:
            return f"你尚未绑定B站账号。请私聊我然后发送\"#绑定\"以完成绑定。"

        try:
            postfix = int(msg[3:])
            assert postfix > 0
            bili_uid = postfix
        except (ValueError, TypeError, AssertionError):
            pass

        user = await LTUserCookie.get_by_uid(user_id=bili_uid, available=True)
        if not user:
            return f"未查询到用户「{bili_uid}」。可能用户已过期，请重新登录。"

        bag_list = await BiliApi.get_bag_list(user.cookie)
        if not bag_list:
            return f"{user.name}(uid: {user.uid})的背包里啥都没有。"

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
        return f"{user.name}(uid: {user.uid})的背包里有:\n{prompt}。"

    async def proc_dynamic(self, msg):
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

    async def proc_query_guard(self, msg):
        user_name_or_uid = msg[4:].strip()
        if not user_name_or_uid:
            bili_uid = await BiliToQQBindInfo.get_by_qq(qq=self.user_id)
        else:
            if user_name_or_uid.isdigit():
                bili_uid = int(user_name_or_uid)
            else:
                bili_uid = await ReqFreLimitApi.get_uid_by_name(user_name_or_uid)

        if not bili_uid:
            return f"指令错误，不能查询到用户: {user_name_or_uid}"

        return await ReqFreLimitApi.get_guard_record(uid=int(bili_uid))

    async def proc_bind(self):
        message = ""
        bili_uid_list = await BiliToQQBindInfo.get_all_bili(qq=self.user_id)

        if len(bili_uid_list) > 0:
            message += f"你已经绑定到Bili用户:\n{'、'.join([str(_) for _ in bili_uid_list])}。绑定更多账号请按如下操作：\n"

        code = f"{randint(0x1000, 0xffff):0x}"
        key = f"BILI_BIND_CHECK_KEY_{code}"
        if await redis_cache.set_if_not_exists(key=key, value=self.user_id, timeout=3600):
            message += f"请你现在去1234567直播间发送以下指令:\nhttps://live.bilibili.com/1234567\n\n你好{code}"
        else:
            message += f"操作失败！系统繁忙，请5秒后再试。"

        return message

    async def proc_unbind(self):
        return f"要想解绑，请你现在去1234567直播间发送:\n\n再见"

    async def proc_chicken(self):
        user_id = self.user_id

        if user_id != g.QQ_NUMBER_DD:
            if not await redis_cache.set_if_not_exists(f"LT_PROC_CHICKEN_{user_id}", 1, timeout=180):
                ttl = await redis_cache.ttl(f"LT_PROC_CHICKEN_{user_id}")
                self.response(f"请{ttl}秒后再发送此命令。")
                return

        last_active_time = await redis_cache.get("LT_LAST_ACTIVE_TIME")
        if not isinstance(last_active_time, int):
            last_active_time = 0
        last_active_time = int(time.time()) - last_active_time

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

        all_gifts = await DelayAcceptGiftsQueue.get_all()
        gifts = []
        score = []
        for i, gift in enumerate(all_gifts):
            if i % 2 == 0:
                gifts.append(gift)
            else:
                score.append(gift)

        message = f"辣🐔最后活跃时间: {gen_time_prompt(last_active_time)}，队列中有{len(gifts)}个未收大宝贝：\n\n{'-'*20}\n"

        prompt_gift_list = []
        for i, gift in enumerate(gifts):
            room_id = gift["room_id"]
            gift_name = gift["gift_name"]

            room_id = int(room_id)
            accept_time = -1 * int(time.time() - score[i])
            if accept_time < 0:
                accept_time = 0
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
        return message

    async def proc_unfreeze(self, msg):
        try:
            bili_uid = int(msg[2:].strip())
        except (IndexError, ValueError, TypeError):
            self.response("指令错误。请发送“解冻”+B站uid， 如:\n解冻731556")
            return

        bili_uids = await BiliToQQBindInfo.get_all_bili(qq=self.user_id)
        if bili_uid not in bili_uids:
            self.response("UID错误。")
            return

        if bili_uid not in await LTTempBlack.get_blocked():
            return f"你（uid: {bili_uid}）没有被冻。此命令会加重辣🐔的工作负担，请不要频繁发送。\n\n爱护辣🐔，人人有责。"

        await LTTempBlack.remove(uid=bili_uid)
        return "操作成功。"

    async def proc_help(self):
        if self.group_id:
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
            if self.user_id == g.QQ_NUMBER_DD:
                message += (
                    f"\n"
                    f"ac、dc、auc: 辣条白名单\n"
                    f"as、ds: 超级答谢鸡\n"
                    f"++123+1212、--33234: 绑定解绑\n"
                    f"approve、11、33、44、g、r"
                )
        return message


class BotHandler:

    @classmethod
    async def handle_group_message(cls, msg, user_id, group_id):
        msg = msg.replace("＃", "#")

        p = BotUtils(user_id=user_id, group_id=group_id)
        if msg in ("一言", "#一言"):
            return await p.proc_one_sentence()

        elif msg.startswith("#点歌"):
            return await p.proc_song(msg)

        elif msg.startswith("#翻译"):
            return p.proc_translation(msg)

        elif msg.startswith("#动态"):
            return await p.proc_dynamic(msg)

        elif msg.lower() in ("#h", "#help", "#帮助", "#指令"):
            return await p.proc_help()

    @classmethod
    async def handle_private_message(cls, msg, user_id):
        if user_id == g.QQ_NUMBER_DD:
            if msg.startswith("approve"):
                try:
                    _, flag, sub_type = msg.strip().split("$")
                except (TypeError, ValueError, IndexError):
                    return

                if sub_type:
                    r = await async_zy.set_group_add_request(flag=flag, sub_type=sub_type, approve=True)
                else:
                    r = await async_zy.set_friend_add_request(flag=flag, approve=True)
                return f"已通过：{r}"

            elif msg.startswith("ac"):
                account = msg[2:]
                r = await LTUserCookie.add_uid_or_account_to_white_list(account=account)
                return f"白名单已添加: {account}, id: {r}"

            elif msg.startswith("auc"):
                uid, account = msg[3:].split("-", 1)
                r = await LTUserCookie.add_uid_or_account_to_white_list(uid=int(uid), account=account)
                return f"白名单已添加: {account}, uid: {uid}, id: {r}"

            elif msg.startswith("dc"):
                account = msg[2:]
                r = await LTUserCookie.del_uid_or_account_from_white_list(account=account)
                return f"白名单已删除: {account}, id: {r}"

            elif msg.startswith("33"):
                message = msg[2:]
                dd_obj = await LTUserCookie.get_by_uid("DD")
                await BiliApi.send_danmaku(message=message, room_id=13369254, cookie=dd_obj.cookie)
                return

            elif msg.startswith("++"):
                qq, bili = [int(_) for _ in msg[2:].split("+")]
                r = await BiliToQQBindInfo.bind(qq=qq, bili=bili)
                all_bili = await BiliToQQBindInfo.get_all_bili(qq=qq)
                message = f"绑定结果: {r}。{qq} -> {'、'.join([str(b) for b in all_bili])}"
                return message

            elif msg.startswith("--"):
                bili = int(msg[2:])
                qq = await BiliToQQBindInfo.unbind(bili=bili)
                if qq:
                    all_bili = await BiliToQQBindInfo.get_all_bili(qq=qq)
                else:
                    all_bili = []
                message = f"解绑。{qq} -> {'、'.join([str(b) for b in all_bili])}"
                return message

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

        p = BotUtils(user_id=user_id, group_id=None)
        if msg.startswith("#背包"):
            return await p.proc_query_bag(msg)

        elif msg.startswith("#动态"):
            return await p.proc_dynamic(msg)

        elif msg.startswith("#大航海"):
            return await p.proc_query_guard(msg)

        elif msg.startswith("#中奖查询"):
            return await p.proc_query_raffle(msg)

        elif msg.startswith("#勋章查询"):
            return ""

        elif msg.startswith("#挂机查询"):
            return await p.proc_lt_status(msg)

        elif msg.startswith("#绑定"):
            return await p.proc_bind()

        elif msg.startswith("#解绑"):
            return await p.proc_unbind()

        elif msg.lower() in ("#h", "#help", "#帮助", "#指令"):
            return await p.proc_help()

        elif msg == "lt":
            token = f"{random.randint(0x100000000000, 0xFFFFFFFFFFFF):0x}"
            key = F"LT_ACCESS_TOKEN_{token}"
            await redis_cache.incr(key=key)
            await redis_cache.expire(key=key, timeout=180)

            logging.info(F"LT_ACCESS_TOKEN_GEND: {token}, user_id: {user_id}")

            key = f"LT_WEB_{user_id}"
            web_token = await redis_cache.get(key=key)
            if not web_token:
                web_token = token
                await redis_cache.set(key=key, value=web_token, timeout=3600*24*30)

            message = (
                f"宝藏站点地址: \nhttp://www.madliar.com:2020/lt_{token}\n\n"
                f"如果无法使用密码登录，请使用二维码扫码登录：\nhttp://www.madliar.com:2020/lt/qr_code_login/{token}\n\n"
                f"本URL只可一次性使用，如遇404则说明已失效，请重新获取；否则，请一直刷新页面，直到能够正常显示。\n\n"
                "---------------\n"
                "另外，为了防止异常情况导致QQ机器人不可用，你还可以通过web页面发送指令，来查询状态，你的专属地址"
                "（此链接有效期一个月，请保存浏览器标签，并且不要告知他人）：\n"
                f"https://www.madliar.com/bili/q/{user_id}/{web_token}"
            )
            return message

        elif msg in ("鸡", "🐔"):
            return await p.proc_chicken()

        elif msg.startswith("解冻"):
            return await p.proc_unfreeze(msg)

    @classmethod
    async def handle_message(cls, context):
        if context["message_type"] == "group":
            sender = context["sender"]
            user_id = sender["user_id"]
            user_nickname = sender["nickname"]
            title = sender.get("title", "--")
            card = sender.get("card", "--")
            group_id = context["group_id"]
            msg = context["message"]
            logging.info(f"群消息: ({group_id}) [{title}][{card}]{user_nickname}({user_id}) -> {msg}")

            response = await cls.handle_group_message(msg, user_id, group_id)
            if response:
                await async_zy.send_group_msg(group_id=group_id, message=response)

        elif context["message_type"] == "private":
            user_id = context["sender"]["user_id"]
            msg = context["raw_message"]
            try:
                response = await cls.handle_private_message(msg=msg, user_id=user_id)
            except Exception as e:
                response = f"在处理命令[{msg}]时发生了不可处理的错误，请稍后再试。\n\n{e}\n\n{traceback.format_exc()}"

            if response:
                await async_zy.send_private_msg(user_id=user_id, message=response)

        return

    @classmethod
    async def handle_request(cls, context):
        if context["request_type"] == "group":
            postfix = f"梓亚收到【加群】请求\n\napprove${context['flag']}${context['sub_type']}"
        else:
            postfix = f"梓亚收到【好友】请求\n\napprove${context['flag']}$"

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
            f"验证消息: {context['comment']}\n"
            f"{nickname}({context['user_id']}) - {sex}\n"
            f"年龄: {age}\n"
            f"{postfix}"
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
