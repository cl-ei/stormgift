import re
import json
import time
import asyncio
import requests
from random import random
from math import floor
from config.log4 import bili_api_logger as logging


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


class BiliApi:
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

    @classmethod
    async def _request(cls, method, url, headers, data, timeout, check_response_json, check_error_code):
        if headers:
            headers.update(cls.headers)
        else:
            headers = cls.headers
        fn = requests.post if method == "post" else requests.get
        try:
            r = fn(url=url, data=data, headers=headers, timeout=timeout)
        except Exception as e:
            return False, f"Response Error: {e}"

        if r.status_code != 200:
            return False, f"Status code Error: {r.status_code}"

        if not check_response_json:
            return True, r.text

        try:
            result = json.loads(r.text)
        except Exception as e:
            return False, f"Not json response: {e}"

        if not check_error_code:
            return True, result

        if result.get("code") not in (0, "0"):
            return False, f"Error code not 0! r: {result.get('message')}"
        else:
            return True, result

    @classmethod
    async def get(cls, url, headers=None, data=None, timeout=5, check_response_json=False, check_error_code=False):
        if check_error_code:
            check_response_json = True
        return await cls._request("get", url, headers, data, timeout, check_response_json, check_error_code)

    @classmethod
    async def post(cls, url, headers=None, data=None, timeout=5, check_response_json=False, check_error_code=False):
        if check_error_code:
            check_response_json = True
        return await cls._request("post", url, headers, data, timeout, check_response_json, check_error_code)

    @classmethod
    async def search_live_room(cls, area, old_room_id=None, timeout=5):
        req_url = (
            "https://api.live.bilibili.com/room/v3/area/getRoomList"
            "?platform=web&page=1&page_size=10"
            "&parent_area_id=%s" % area
        )
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        room_id = 0
        room_info_list = r.get("data", {}).get("list", [])
        for info in room_info_list:
            room_id = int(info.get("roomid", 0))
            if room_id and room_id != old_room_id:
                break
        if room_id:
            return True, room_id
        else:
            return False, f"Response data error: {r}"

    @classmethod
    async def check_live_status(cls, room_id, area=None, timeout=5):
        if not room_id:
            return True, False

        req_url = (
            "https://api.live.bilibili.com/AppRoom/index"
            "?platform=android&room_id=%s" % room_id
        )
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            if "房间已经被锁定" in r:
                return True, False
            return False, r

        data = r.get("data", {})
        is_lived = data.get("status") == "LIVE"
        if area is None:
            return True, is_lived
        else:
            return True, is_lived and data.get("area_v2_parent_id") == area

    @classmethod
    async def get_tv_raffle_id(cls, room_id, timeout=5):
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=%s" % room_id
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        raffle_id_list = r.get("data", {}).get("list", [])
        if raffle_id_list:
            return True, raffle_id_list
        else:
            return False, f"Empty raffle_id_list in response."

    @classmethod
    async def get_guard_raffle_id(cls, room_id, timeout=5):
        req_url = "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=%s" % room_id
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return flag, r

        raffle_id_list = r.get("data", [])
        if not raffle_id_list:
            return False, f"Empty raffle_id_list in response."

        return_data = {}
        for raffle in raffle_id_list:
            raffle_id = raffle.get("id", 0)
            if raffle_id:
                return_data[raffle_id] = raffle

        return_data = return_data.values()
        if return_data:
            return True, return_data
        else:
            return False, f"Cannot get valid raffleId from list, r:{r}"

    @classmethod
    async def get_guard_room_list(cls, timeout=5):
        req_url = "https://bilipage.expublicsite.com:23333/Governors/SimpleView"
        flag, r = await cls.get(req_url, timeout=timeout)
        if not flag:
            return False, r

        room_list = re.findall(r"https://live.bilibili.com/(\d+)", r)
        result = set()
        for room_id in room_list:
            try:
                result.add(int(room_id))
            except (ValueError, TypeError):
                pass

        if not result:
            return False, f"Empty list in response."
        else:
            return True, result

    @classmethod
    async def get_user_id_by_search_way(cls, name, timeout=5):
        req_url = "https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=%s" % name
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        result_list = r.get("data", {}).get("result", []) or []
        if not result_list:
            return False, "No result."

        for r in result_list:
            if r.get("uname") == name:
                return True, int(r.get("mid", 0)) or None
        return False, f"Cannot find uid from response. r: {r}"

    @classmethod
    async def add_admin(cls, name, cookie, timeout=5):
        try:
            anchor_id = re.findall(r"DedeUserID=(\d+)", cookie)[0]
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            return False, f"Bad cookie! {cookie}"

        req_url = "https://api.live.bilibili.com/live_user/v1/RoomAdmin/add"
        headers = {"Cookie": cookie}
        data = {
            "admin": name,
            "anchor_id": anchor_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r
        if r.get("code") == 0:
            return True, None
        else:
            return False, r.get("msg", "") or "Known error."

    @classmethod
    async def get_admin_list(cls, cookie, timeout=5):
        req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/get_by_anchor?page=1"
        headers = {"Cookie": cookie}
        flag, r = await cls.get(req_url, headers=headers, timeout=timeout,
                                check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        result = r.get("data", {}).get("data", []) or []
        return bool(result), result or "Empty admin list."

    @classmethod
    async def remove_admin(cls, uid, cookie, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            return False

        req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/dismiss"
        headers = {"Cookie": cookie}
        data = {
            "uid": uid,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r
        if r.get("code") == 0:
            return True, None
        else:
            return False, r.get("message", "") or "Known error."

    @classmethod
    async def join_tv(cls, room_id, gift_id, cookie, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/join"
        headers = {"Cookie": cookie}
        data = {
            "roomid": room_id,
            "raffleId": gift_id,
            "type": "Gift",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, r = await cls.post(req_url, timeout=timeout, headers=headers, data=data, check_response_json=True)
        if not flag:
            return flag, r

        result = r.get("code") == 0
        if result:
            return True, f"OK gift_type: {r.get('data', {}).get('type')}"
        else:
            return False, r.get("msg", "-")

    @classmethod
    async def join_guard(cls, room_id, gift_id, cookie, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/lottery/v2/Lottery/join"
        headers = {"Cookie": cookie}
        data = {
            "roomid": room_id,
            "id": gift_id,
            "type": "guard",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        result = r.get("code") == 0
        if result:
            data = r.get("data", {})
            return True, f"{data.get('message')}, from {data.get('from')}"
        else:
            return False, r.get("msg", "-")

    @classmethod
    async def send_danmaku(cls, message, room_id, cookie, color=0xffffff, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://live.bilibili.com/msg/send"
        headers = {"Cookie": cookie}
        data = {
            "color": color,
            "fontsize": 25,
            "mode": 1,
            "msg": message,
            "rnd": int(time.time()),
            "roomid": room_id,
            "csrf_token": csrf_token,
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        result = r.get("code") == 0
        if result:
            return True, r.get("message", "")
        else:
            return False, r.get("message", "-")

    @classmethod
    async def enter_room(cls, room_id, cookie, timeout=5):
        headers = {"Cookie": cookie}

        req_url = f"https://api.live.bilibili.com/live_user/v1/UserInfo/get_info_in_room?roomid={room_id}"
        await cls.get(req_url, headers=headers, timeout=timeout, check_response_json=True)

        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"
        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/room/v1/Room/room_entry_action"
        data = {
            "room_id": room_id,
            "platform": "pc",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        return r

    @classmethod
    async def get_user_face(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/space/acc/info?jsonp=jsonp&mid={uid}"
        flag, data = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if not flag:
            return ""
        else:
            return data.get("data", {}).get("face", "") or ""

    @classmethod
    async def get_uid_by_live_room_id(cls, room_id, timeout=10):
        req_url = f"https://live.bilibili.com/{room_id}"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        flag, data = await cls.get(req_url, headers=headers, timeout=timeout)
        if not flag:
            return -1

        try:
            uid = int(re.search(r"\"uid\"\:(\d+)", data).groups()[0])
        except Exception:
            uid = -1
        return uid

    @classmethod
    async def get_fans_list(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/relation/followers?vmid={uid}&pn=1&ps=50&order=desc&jsonp=jsonp"
        flag, data = await cls.get(req_url, timeout=timeout, check_error_code=True)
        result = []
        if not flag:
            return result
        for d in data.get("data", {}).get("list", []):
            result.append({"mid": d.get("mid"), "uname": d.get("uname")})
        return result

    @classmethod
    async def get_fans_count_by_uid(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/relation/followers?vmid={uid}&pn=1&ps=50&order=desc&jsonp=jsonp"
        flag, data = await cls.get(req_url, timeout=timeout, check_error_code=True)
        result = 0
        if not flag:
            return result
        count = data.get("data", {}).get("total", 0)
        return int(count)

    @classmethod
    async def get_guard_live_room_id_list(cls, cookie, page=1, timeout=10):
        if page >= 5:
            return []

        result = []
        req_url = f"https://api.live.bilibili.com/i/api/guard?page={page}&pageSize=10"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if not flag:
            return result

        data = r.get("data", {})
        for g in data.get("list", []):
            if "201" in g.get("expired_date", ""):
                result.append(int(g.get("ruid")))

        page_info = data.get("pageinfo", {}) or {}
        total = page_info.get("totalPage", 1)
        current = page_info.get("curPage", 1)
        if total <= current:
            return list(set(result))

        others = await cls.get_guard_live_room_id_list(cookie, page + 1)
        result.extend(others)
        return list(set(result))

    @classmethod
    async def get_live_room_id_by_uid(cls, uid, timeout=10):
        req_url = f"http://api.live.bilibili.com/room/v1/Room/getRoomInfoOld?mid={uid}"
        flag, r = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("roomid", -1) or -1
        return -1

    @classmethod
    async def get_medal_info_list(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/i/api/medal?page=1&pageSize=30"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("fansMedalList", []) or []
        return []

    @classmethod
    async def get_bag_list(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/gift/v2/gift/bag_list"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("list", []) or []
        return []

    @classmethod
    async def get_wallet(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/pay/v2/Pay/myWallet?need_bp=1&need_metal=1&platform=pc"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}) or {}
        return {}

    @classmethod
    async def send_gift(cls, gift_id, gift_num, coin_type, bag_id, ruid, live_room_id, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/gift/v2/live/bag_send"
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"
        csrf_token = csrf_token_list[0]

        uid_list = re.findall(r"DedeUserID=(\d+)", cookie)
        if not uid_list:
            return False, f"Bad cookie, cannot get uid."
        uid = int(uid_list[0])

        headers = {"Cookie": cookie}
        data = {
            "uid": uid,
            "gift_id": gift_id,
            "ruid": ruid,
            "gift_num": gift_num,
            "coin_type": coin_type,
            "bag_id": bag_id,
            "platform": "pc",
            "biz_code": "live",
            "biz_id": live_room_id,
            "rnd": int(time.time()),
            "storm_beat_id": 0,
            "metadata": "",
            "price": 0,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        return await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)

    @classmethod
    async def get_guard_list(cls, uid, room_id=None, timeout=10):
        if not room_id:
            room_id = await cls.get_live_room_id_by_uid(uid)
            if room_id <= 0:
                return []

        result = {}
        page = 1
        for _ in range(20):
            req_url = f"https://api.live.bilibili.com/guard/topList?roomid={room_id}&page={page}&ruid={uid}"
            flag, data = await cls.get(req_url, timeout=timeout, check_error_code=True)

            if not flag:
                await asyncio.sleep(1)
                continue

            data = data.get("data", {}) or {}
            guard_list = data.get("list", []) + data.get("top3", [])
            for g in guard_list:
                if g["uid"] in result:
                    continue
                result[g["uid"]] = {
                    "uid": g["uid"],
                    "name": g["username"],
                    "level": g["guard_level"]
                }

            current_page = data.get("info", {}).get("page", 0)
            if page >= current_page:
                break
            else:
                page += 1
        return sorted(result.values(), key=lambda x: x["level"])

    @classmethod
    async def post_heartbeat_5m(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/User/userOnlineHeart"
        headers = {"Cookie": cookie}
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"
        data = {"csrf_token": csrf_token, "csrf": csrf_token}
        return await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)

    @classmethod
    async def post_heartbeat_last_timest(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/relation/v1/feed/heartBeat?_={int(1000 * time.time())}"
        headers = {"Cookie": cookie}
        return await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)

    @classmethod
    async def do_sign(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/sign/doSign"
        headers = {"Cookie": cookie}
        return await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)

    @classmethod
    async def _sing_single_group(cls, group_id, owner_id, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/link_setting/v1/link_setting/sign_in"
        headers = {"Cookie": cookie}
        data = {
            "group_id": group_id,
            "owner_id": owner_id,
        }
        r, data = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)
        return r, data

    @classmethod
    async def do_sign_group(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/link_group/v1/member/my_groups"
        headers = {"Cookie": cookie}
        r, data = await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)
        if not r:
            return r, data

        groups = data.get("data", {}).get("list", []) or []
        failed_info = ""
        for g in groups:
            r, data = await cls._sing_single_group(g.get("group_id", 0), owner_id=g.get("owner_uid", 0), cookie=cookie)
            if not r:
                failed_info += f"group sign faild: {g.get('group_name', '--')}, msg: {data}.\n"
        return True, failed_info

    @classmethod
    async def do_sign_double_watch(cls, cookie, timeout=10):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        req_url = "https://api.live.bilibili.com/activity/v1/task/receive_award"
        headers = {"Cookie": cookie}
        data = {
            "task_id": "double_watch_task",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
        }
        r, data = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)
        return r, data

    @classmethod
    async def silver_to_coin(cls, cookie, timeout=10):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        req_url = "https://api.live.bilibili.com/pay/v1/Exchange/silver2coin"
        headers = {"Cookie": cookie}
        data = {
            "platform": "pc",
            "csrf_token": csrf_token
        }
        return await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)

    @classmethod
    async def get_if_user_is_live_vip(cls, cookie, user_id=None, timeout=10):
        req_url = "https://api.live.bilibili.com/xlive/web-ucenter/user/get_user_info"
        headers = {"Cookie": cookie}
        r, data = await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)
        if not r:
            return r, data

        if isinstance(user_id, int) and user_id != data.get("data", {}).get("uid"):
            return False, "User id not match."

        result = data.get("data", {}).get("vip") == 1
        return True, result

    @classmethod
    async def get_live_status(cls, room_id, timeout=10):
        req_url = F"https://api.live.bilibili.com/AppRoom/index?room_id={room_id}&platform=android"
        r, data = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if not r:
            if "房间已经被锁定" in data:
                return True, False
            return False, data
        result = data.get("data", {}).get("status") == "LIVE"
        return True, result

    @classmethod
    async def force_get_real_room_id(cls, room_id, timeout=10):
        from utils.dao import redis_cache

        redis_cache_key = f"REAL_ROOM_ID_OF_{room_id}"
        real_room_id = await redis_cache.get(redis_cache_key)
        if isinstance(real_room_id, int) and real_room_id > 0:
            logging.info(f"BILI_API Get real room id: {room_id} -> {real_room_id} by redis.")
            return real_room_id

        req_url = f"https://api.live.bilibili.com/AppRoom/index?room_id={room_id}&platform=android"
        r, data = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if not r:
            logging.error(f"BILI_API Cannot get real room id of {room_id}: {data}.")
            return room_id

        real_room_id = data.get("data", {}).get("room_id")
        if isinstance(real_room_id, int) and real_room_id > 0:
            r = await redis_cache.set(redis_cache_key, real_room_id, timeout=3600*24*200)
            logging.info(f"BILI_API Get real room id: {room_id} -> {real_room_id}, saved to redis: {r}.")
            room_id = real_room_id
        return room_id


async def test():
    print("Running test.")
    r = await BiliApi.get_live_status(2516117)
    print(r)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
    loop.close()
