import re
import json
import aiohttp
from random import random
from math import floor
from config.log4 import api_logger as logging


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
    async def search_live_room(cls, area, old_room_id=None, timeout=5):
        req_url = (
            "https://api.live.bilibili.com/room/v3/area/getRoomList"
            "?platform=web&page=1&page_size=10"
            "&parent_area_id=%s" % area
        )
        r = {}
        timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            pass

        room_id = 0
        room_info_list = r.get("data", {}).get("list", [])
        for info in room_info_list:
            room_id = int(info.get("roomid", 0))
            if room_id and room_id != old_room_id:
                break
        return room_id

    @classmethod
    async def check_live_status(cls, room_id, area=None, timeout=5):
        if not room_id:
            return True, False

        req_url = (
            "https://api.live.bilibili.com/AppRoom/index"
            "?platform=android&room_id=%s" % room_id
        )
        r = {}
        timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Error in check_live_status e: {str(e)}.", exc_info=True)
            return False, False

        if r.get("code") not in (0, "0"):
            logging.error(f"Error in check_live_status response code is not 0. r: {r}")
            return False, False

        data = r.get("data", {})
        is_lived = data.get("status") == "LIVE"
        if area is None:
            return True, is_lived
        else:
            return True, is_lived and data.get("area_v2_parent_id") == area

    @classmethod
    async def get_tv_raffle_id(cls, room_id, return_detail=False, timeout=5):
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=%s" % room_id
        r = {}
        timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Response error in get_tv_raffle_id, e: {e}")
            return []

        raffle_id_list = r.get("data", {}).get("list", [])
        if return_detail:
            return raffle_id_list

        return_data = set()
        for raffle in raffle_id_list:
            raffle_id = raffle.get("raffleId", 0)
            if raffle_id:
                return_data.add(raffle_id)
        return list(return_data)

    @classmethod
    async def get_guard_raffle_id(cls, room_id, return_detail=False, timeout=5):
        req_url = "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=%s" % room_id
        r = {}
        timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Response error in get_guard_raffle_id, e: {e}")
            return []

        raffle_id_list = r.get("data", [])
        if return_detail:
            return raffle_id_list

        return_data = set()
        for raffle in raffle_id_list:
            raffle_id = raffle.get("id", 0)
            if raffle_id:
                return_data.add(raffle_id)
        return list(return_data)

    @classmethod
    async def get_guard_room_list(cls):
        req_url = "https://dmagent.chinanorth.cloudapp.chinacloudapi.cn:23333/Governors/View"
        r = ""
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = await resp.text()
        except Exception as e:
            logging.error(f"Response error in get_guard_room_list, e: {e}")
            return set()

        room_list = re.findall(r"https://live.bilibili.com/(\d+)", r)
        result = set()
        for room_id in room_list:
            try:
                result.add(int(room_id))
            except (ValueError, TypeError):
                pass
        return result

    @classmethod
    async def _get_user_id_by_search_way(cls, name):
        req_url = "https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=%s" % name
        r = {}
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Error response in _get_user_id_by_search_way, e: {str(e)}")
            return False, None

        if r.get("code") not in (0, "0"):
            logging.error(f"_get_user_id_by_search_way: Response code is not 0! r: {r}.")
            return False, None

        result_list = r.get("data", {}).get("result", []) or []
        for r in result_list:
            if r.get("uname") == name:
                return True, int(r.get("mid", 0)) or None
        return False, None

    @classmethod
    async def _add_admin(cls, name, cookie):
        try:
            anchor_id = re.findall(r"DedeUserID=(\d+)", cookie)[0]
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            return False

        timeout = aiohttp.ClientTimeout(total=5)
        req_url = "https://api.live.bilibili.com/live_user/v1/RoomAdmin/add"
        headers = {"Cookie": cookie}
        headers.update(cls.headers)
        data = {
            "admin": name,
            "anchor_id": anchor_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        r = {}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(req_url, data=data) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Cannot set admin({name})! e: {str(e)}")
            return False
        return r.get("code") == 0

    @classmethod
    async def _get_admin_list(cls, cookie):
        req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/get_by_anchor?page=1"
        headers = {"Cookie": cookie}
        headers.update(cls.headers)
        timeout = aiohttp.ClientTimeout(total=5)
        r = {}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(req_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Response error! {str(e)}.", exc_info=True)
            return []

        if r.get("code") not in (0, "0"):
            logging.error(f"_get_admin_list Response code is not 0! r: {r}.")
            return []

        return r.get("data", {}).get("data", []) or []

    @classmethod
    async def _remove_admin(cls, uid, cookie):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            return False

        timeout = aiohttp.ClientTimeout(total=5)
        req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/dismiss"
        headers = {"Cookie": cookie}
        headers.update(cls.headers)
        data = {
            "uid": uid,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        r = {}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(req_url, data=data) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            logging.error(f"Can not remove admin(uid: {uid}). e: {str(e)}")
            return False
        return r.get("code") == 0

    @classmethod
    async def _get_user_id_by_admin_list(cls, name, cookie):
        await cls._add_admin(name, cookie)

        admin_list = await cls._get_admin_list(cookie)
        uid = None
        for admin in admin_list:
            if admin.get("uname") == name:
                uid = admin.get("uid")
                break
        if uid:
            await cls._remove_admin(uid, cookie)
        return uid

    @classmethod
    async def get_user_id_by_name(cls, name, cookie, retry_times=1):
        for retry_time in range(retry_times):
            r, uid = await cls._get_user_id_by_search_way(name)
            if r:
                return True, uid
            uid = await cls._get_user_id_by_admin_list(name, cookie)
            if uid:
                return True, uid
        return False, None

    @classmethod
    async def join_tv(cls, i, room_id, gift_id, cookie, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            msg = f"Can not get csrf token when join tv. index: {i}, room_id: {room_id}, gift_id: {gift_id}"
            logging.error(msg)
            return False, msg

        timeout = aiohttp.ClientTimeout(total=timeout)
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/join"
        headers = {"Cookie": cookie}
        headers.update(cls.headers)
        data = {
            "roomid": room_id,
            "raffleId": gift_id,
            "type": "Gift",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        r = {}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(req_url, data=data) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            msg = f"Join tv response error: {str(e)}. index: {i}, key: {room_id}${gift_id}"
            logging.error(msg, exc_info=True)
            return False, msg

        result = r.get("code") == 0
        if result:
            return True, f"OK gift_type: {r.get('data', {}).get('type')}"
        else:
            return result, r.get("msg", "-")

    @classmethod
    async def join_guard(cls, i, room_id, gift_id, cookie, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            msg = f"Can not get csrf token when join tv. index: {i}, room_id: {room_id}, gift_id: {gift_id}"
            logging.error(msg)
            return False, msg

        timeout = aiohttp.ClientTimeout(total=timeout)
        req_url = "https://api.live.bilibili.com/lottery/v2/Lottery/join"
        headers = {"Cookie": cookie}
        headers.update(cls.headers)
        data = {
            "roomid": room_id,
            "id": gift_id,
            "type": "guard",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        r = {}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(req_url, data=data) as resp:
                    if resp.status != 200:
                        raise Exception(f"Response status error! ({resp.status})")
                    r = json.loads(await resp.text())
        except Exception as e:
            msg = f"Join guard response error: {str(e)}. index: {i}, room_id: {room_id}, gift_id: {gift_id}"
            logging.error(msg, exc_info=True)
            return False, msg

        result = r.get("code") == 0
        if result:
            data = r.get("data", {})
            return True, f"{data.get('message')}, from {data.get('from')}"
        else:
            return False, r.get("msg", "-")
