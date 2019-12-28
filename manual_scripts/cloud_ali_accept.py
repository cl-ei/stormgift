import re
import json
import asyncio
import aiohttp
import logging

logging = logging.getLogger()


async def request(method, url, headers, data):
    default_headers = {
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
    headers.update(default_headers)
    client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    try:
        async with client_session as session:
            async with session.request(method, url, data=data, headers=headers) as resp:
                status_code = resp.status
                if status_code != 200:
                    return status_code, f"{status_code}"

                content = await resp.text()
                return status_code, content
    except Exception as e:
        return 5000, f"{e}"


class Executor:
    def __init__(self, act, room_id, gift_id, cookie, gift_type):
        self.act = act
        self.room_id = room_id
        self.gift_id = gift_id
        self.cookie = cookie
        self.gift_type = gift_type

    async def run(self):
        target = getattr(self, self.act, None)
        if target:
            return await target()
        else:
            return [False, F"CLOUD NO HANDLER: {self.act}"]

    async def join_tv_v5(self):
        csrf_token = re.findall(r"bili_jct=(\w+)", self.cookie)[0]
        req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v5/smalltv/join"
        headers = {
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://live.bilibili.com",
            "Referer": "https://live.bilibili.com/%s" % self.room_id,
            "Sec-Fetch-Mode": "cors",
        }
        data = {
            "id": self.gift_id,
            "roomid": self.room_id,
            "type": self.gift_type,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        status_code, content = await request(method="post", url=req_url, headers=headers, data=data)
        if status_code != 200:
            return False, content

        r = json.loads(content)
        if r.get("code") != 0:
            return False, r.get("msg", "-") or r.get("message")

        award_name = r["data"]['award_name']
        award_num = r["data"]['award_num']
        return True, f"{award_num}_{award_name}"

    async def join_guard(self):
        csrf_token = re.findall(r"bili_jct=(\w+)", self.cookie)[0]
        req_url = "https://api.live.bilibili.com/lottery/v2/Lottery/join"
        headers = {"Cookie": self.cookie}
        data = {
            "roomid": self.room_id,
            "id": self.gift_id,
            "type": "guard",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        status_code, content = await request(method="post", url=req_url, headers=headers, data=data)
        if status_code != 200:
            return False, content

        r = json.loads(content)
        if r.get("code") != 0:
            return False, r.get("msg", "-") or r.get("message")

        message = r["data"]['message']
        award_name = "辣条" if "辣条" in message else "亲密度"
        privilege_type = r["data"]['privilege_type']
        if privilege_type == 3:
            award_num = 1
        elif privilege_type == 2:
            award_num = 5
        elif privilege_type == 1:
            award_num = 20
        else:
            award_num = 1
        return True, f"{award_num}_{award_name}"

    async def join_pk(self):
        csrf_token = re.findall(r"bili_jct=(\w+)", self.cookie)[0]
        req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v1/pk/join"
        headers = {"Cookie": self.cookie}
        data = {
            "roomid": self.room_id,
            "id": self.gift_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        status_code, content = request(method="post", url=req_url, headers=headers, data=data)
        if status_code != 200:
            return False, content

        r = json.loads(content)
        if r.get("code") != 0:
            return False, r.get("msg", "-") or r.get("message")

        award_name = r["data"]['award_text']
        award_num = r["data"]['award_num']
        return True, f"{award_num}_{award_name}"


async def main(act, room_id, gift_id, cookies, gift_type=""):
    executors = [Executor(act, room_id, gift_id, c, gift_type).run() for c in cookies]
    return await asyncio.gather(*executors)


def handler(environ, start_response):
    """ for aliyun. """
    start_response('200 OK', [('Content-type', 'application/json')])
    request_body = environ['wsgi.input'].read(int(environ['CONTENT_LENGTH']))
    request_params = json.loads(request_body)

    loop = asyncio.get_event_loop()
    r = loop.run_until_complete(main(**request_params))

    return [json.dumps(r, ensure_ascii=False).encode()]


def main_handler(event, context):
    """ for tencent. """
    request_params = json.loads(event["body"])

    loop = asyncio.get_event_loop()
    r = loop.run_until_complete(main(**request_params))

    return {
        "headers": {"Content-Type": "application/json"},
        "statusCode": 200,
        "body": json.dumps(r, ensure_ascii=False)
    }
