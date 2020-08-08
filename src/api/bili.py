import time
import uuid
import json
import base64
import hashlib
import aiohttp
from urllib.parse import urlencode

from config.log4 import bili_api_logger as logging
from config import cloud_function_url, cloud_get_uid
from src.api.schemas import *
from src.db.models.lt_user import LTUser


class BiliApiError(Exception):
    def __init__(self, message: str):
        self.message = message


class _BiliApi:
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/84.0.4147.105 Safari/537.36"
    )
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,image/apng,*/*;q=0.8"
        ),
        "User-Agent": UA,
    }

    appkey = "1d8b6e7d45233436"
    actionKey = "appkey"
    build = "520001"
    device = "android"
    mobi_app = "android"
    platform = "android"
    app_secret = "560c52ccd288fed045859ed18bffd973"

    app_headers = {
        "User-Agent": "Mozilla/5.0 BilidDroid/5.51.1(bbcallen@gmail.com)",
        "Accept-encoding": "gzip",
        "Buvid": "000ce0b9b9b4e342ad4f421bcae5e0ce",
        "Display-ID": "146771405-1521008435",
        "Accept-Language": "zh-CN",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Connection": "keep-alive",
    }
    app_params = (
        f'actionKey={actionKey}'
        f'&appkey={appkey}'
        f'&build={build}'
        f'&device={device}'
        f'&mobi_app={mobi_app}'
        f'&platform={platform}'
    )

    def __init__(self, raise_exc: bool):
        self.raise_exc = raise_exc

    @classmethod
    async def _request(
            cls,
            method,
            url,
            headers,
            params,
            data,
            timeout: int,
    ) -> Tuple[int, str]:

        timeout = aiohttp.ClientTimeout(total=timeout)
        inner_headers: dict = dict(**cls.headers)
        if headers:
            inner_headers.update(headers)

        if url in (
            "https://api.bilibili.com/x/relation/followers?pn=1&ps=50&order=desc&jsonp=jsonp",
            "https://api.live.bilibili.com/room/v1/Room/room_init",
            "https://api.live.bilibili.com/msg/send",
        ):
            req_json = {
                "method": method,
                "url": url,
                "headers": inner_headers,
                "data": data,
                "params": params,
                "timeout": 60
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(cloud_function_url, json=req_json) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding="utf-8", errors="ignore")
                    return status_code, content

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method=method, url=url, params=params, data=data, headers=inner_headers) as resp:
                status_code = resp.status
                content = await resp.text(encoding="utf-8", errors="ignore")
                return status_code, content

    def parse_response_data(self, response: Dict) -> Optional[Dict]:
        api_error_code = response.get("code")
        if api_error_code != 0:
            if not self.raise_exc:
                return None

            m1 = response.get("message")
            m2 = response.get("msg")
            error_message = f"[{api_error_code}]{m1 or m2}"
            raise BiliApiError(error_message)
        return response.get("data")

    async def safe_request(
            self,
            method: str,
            url: str,
            headers: Dict[str, Any] = None,
            params: Dict[str, Any] = None,
            data: Dict[str, Any] = None,
            timeout: int = 20,
            response_class: Type[Any] = None,
    ) -> Optional[Union[Dict, List]]:
        try:
            status, content = await self._request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                timeout=timeout,
            )
            assert status == 200
            response = json.loads(content)
        except Exception as e:
            logging.error(f"Error in request: {url}\n\te: {e}")
            return None

        data = self.parse_response_data(response)
        if not data or response_class is None:
            return data

        if isinstance(response_class, list):
            return [response_class[0](**d) for d in data]
        else:
            return response_class(**data)


class BiliPublicApi(_BiliApi):
    def __init__(self, raise_exc: bool = False):
        super(BiliPublicApi, self).__init__(raise_exc)

    async def get_live_room_info(self, user_id: int) -> Optional[RoomBriefInfo]:
        req_params = {
            "method": "get",
            "url": "https://api.live.bilibili.com/room/v1/Room/getRoomInfoOld",
            "params": {"mid": user_id},
            "response_class": RoomBriefInfo,
        }
        return await self.safe_request(**req_params)

    async def get_live_room_detail(self, room_id: int) -> Optional[RoomDetailInfo]:
        req_params = {
            "method": "get",
            "url": "https://api.live.bilibili.com/room/v1/Room/get_info",
            "params": {"room_id": int(room_id)},
            "response_class": RoomDetailInfo,
        }
        return await self.safe_request(**req_params)

    async def get_xlive_room_info(self, room_id: int) -> Optional[XLiveRoomInfo]:
        req_params = {
            "method": "get",
            "url": "https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom",
            "params": {"room_id": int(room_id)},
            "response_class": XLiveRoomInfo,
        }
        return await self.safe_request(**req_params)

    @staticmethod
    async def get_uid_by_name(user_name: str) -> Optional[int]:
        from src.db.queries.queries import queries

        user = await queries.get_lt_user_by_uid("DD")
        cookie = user.cookie
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(cloud_get_uid, json={"cookie": cookie, "name": user_name}) as resp:
                    status_code = resp.status
                    content = await resp.text()
        except Exception as e:
            status_code = 5000
            content = f"Error: {e}"

        if status_code != 200:
            logging.error(f"Error happened when get_uid_by_name({user_name}), content: {content}.")
            return None

        try:
            r = json.loads(content)
            assert len(r) == 2
        except (json.JSONDecodeError, AssertionError) as e:
            logging.error(f"Error happened when get_uid_by_name({user_name}), e: {e}, content: {content}")
            return None

        flag, result = r
        if not flag:
            logging.error(f"Cannot get_uid_by_name by cloud_func, name: {user_name}, reason: {result}")
            return None
        return result


class BiliPrivateApi(_BiliApi):

    def __init__(self, req_user: LTUser, raise_exc: bool = False):
        super(BiliPrivateApi, self).__init__(raise_exc)
        self.req_user = req_user
        self.headers = {"Cookie": self.req_user.cookie}

    @staticmethod
    async def encrypt_heart_s(data: Dict[str, Any]) -> Dict[str, Any]:
        url = "http://www.madliar.com:6000/enc"
        try:
            async with aiohttp.request("post", url=url, json=data) as resp:
                s = (await resp.json(content_type=None))["s"]
        except Exception as e:
            _ = e
            s = {}
        return s

    def calc_sign(self, string: str, app_secret: str = None) -> str:
        string += app_secret or self.app_secret
        hash_obj = hashlib.md5()
        hash_obj.update(string.encode('utf-8'))
        sign = hash_obj.hexdigest()
        return sign

    async def storm_heart_e(self, room_id: int) -> HeartBeatEResp:

        public_api = BiliPublicApi(raise_exc=self.raise_exc)
        room_info = await public_api.get_live_room_detail(room_id)
        parent_area_id = room_info.parent_area_id
        area_id = room_info.area_id
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://live.bilibili.com",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        headers.update(self.headers)

        payload = {
            "id": [parent_area_id, area_id, 0, room_info.room_id],
            "device": f'["{self.calc_sign(str(uuid.uuid4()))}","{uuid.uuid4()}"]',
            "ts": int(time.time()*1000),
            "is_patch": 0,
            "heart_beat": [],
            "ua": self.UA,
            "csrf_token": self.req_user.csrf_token,
            "csrf": self.req_user.csrf_token,
        }

        req_params = {
            "method": "post",
            "url": "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/E",
            "headers": headers,
            "data": urlencode(payload),
        }
        data = await self.safe_request(**req_params)
        return HeartBeatEResp(
            timestamp=data['timestamp'],
            secret_key=data['secret_key'],
            heartbeat_interval=data['heartbeat_interval'],
            secret_rule=data['secret_rule'],
            device=payload["device"],
        )

    async def storm_heart_x(
            self,
            index: int,
            hbe: HeartBeatEResp,
            room_id: int,
            parent_area_id: int = None,
            area_id: int = None,
    ) -> Optional[HeartBeatEResp]:

        if parent_area_id is None or area_id is None:
            x_info = await BiliPublicApi().get_xlive_room_info(room_id)
            parent_area_id = x_info.room_info.parent_area_id
            area_id = x_info.room_info.area_id

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://live.bilibili.com',
            'Referer': f'https://live.bilibili.com/{room_id}',
        }
        headers.update(self.headers)

        payload = {
            'id': [parent_area_id, area_id, index, room_id],
            "device": hbe.device,  # LIVE_BUVID
            "ets": hbe.timestamp,
            "benchmark": hbe.secret_key,
            "time": hbe.heartbeat_interval,
            "ts": int(time.time()) * 1000,
            "ua": self.UA,
        }
        s = await self.encrypt_heart_s({"t": payload, "r": hbe.secret_rule})
        # payload
        payload.update({
            's': s,
            'csrf_token': self.req_user.csrf_token,
            'csrf': self.req_user.csrf_token,
            'visit_id': '',
        })

        req_params = {
            "method": "post",
            "url": "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/X",
            "headers": headers,
            "data": urlencode(payload),
        }
        data = await self.safe_request(**req_params)
        if not data:
            return None

        return HeartBeatEResp(
            timestamp=data['timestamp'],
            secret_key=data['secret_key'],
            heartbeat_interval=data['heartbeat_interval'],
            secret_rule=data['secret_rule'],
            device=hbe.device,
        )

    async def storm_heart_beat(self, previous_interval: int, room_id: int) -> int:
        req_params = {
            "method": "get",
            "url": "https://live-trace.bilibili.com/xlive/rdata-interface/v1/heartbeat/webHeartBeat",
            "headers": self.headers,
            "params": {
                "hb": base64.b64encode(f"{previous_interval}|{room_id}|1|0".encode("utf-8")).decode("utf-8"),
                "pf": "web",
            },
        }
        data = await self.safe_request(**req_params)
        try:
            return int(data["next_interval"])
        except Exception as e:
            logging.error(f"Error in storm_heart_beat: {e}")
        return 3

    async def get_bag_list(self, room_id: int = None) -> List[BagItem]:
        url = "https://api.live.bilibili.com/xlive/web-room/v1/gift/bag_list"
        params = {"t": int(time.time() * 1000)}
        if room_id:
            params["room_id"] = room_id
        data = await self.safe_request("get", url, headers=self.headers, params=params)
        gift_list = data["list"]
        return [BagItem(**i) for i in gift_list]

    async def get_user_owned_medals(self) -> List[UserMedalInfo]:
        url = f"https://api.live.bilibili.com/i/api/medal"
        params = {"page": 1, "pageSize": 30}
        data = await self.safe_request("get", url, headers=self.headers, params=params)
        fans_list = data.get("fansMedalList") or []
        result = [UserMedalInfo(**doc) for doc in fans_list]
        return result

    async def receive_heart_gift(self, room_id: int, area_id: int = None):
        if area_id is None:
            public_api = BiliPublicApi(raise_exc=self.raise_exc)
            room_info = await public_api.get_live_room_detail(room_id)
            area_id = room_info.area_id
        url = "https://api.live.bilibili.com/gift/v2/live/heart_gift_receive"
        params = {"room_id": room_id, "area_v2_id": area_id}
        data = await self.safe_request("get", url, headers=self.headers, params=params)
        print(f"receive_heart_gift data: {data}")
