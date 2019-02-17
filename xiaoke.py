import re
import asyncio
import requests
import json
from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi, BiliApi


MONITOR_ROOM_ID = 11472492


async def load_cookie(index=0):
    try:
        with open("data/cookie.json", "r") as f:
            cookies = json.load(f)
        cookie = cookies.get("RAW_COOKIE_LIST")[index]
    except Exception as e:
        cookie = ""
    user_ids = re.findall(r"DedeUserID=(\d+)", cookie)
    if not user_ids:
        return False, None, None

    uid = int(user_ids[0])
    return True, uid, cookie


async def get_tuling_response(msg):
    api_key = "c83e8c03c71d43b6b0ce271d485896d8"
    url = "http://openapi.tuling123.com/openapi/api/v2"
    req_json = {
        "reqType": 0,
        "perception": {"inputText": {"text": msg}},
        "userInfo": {
            "apiKey": api_key,
            "userId": 248138,
        }
    }
    try:
        r = requests.post(url=url, json=req_json)
        if r.status_code != 200:
            raise Exception(f"Bad status code: {r.status_code}")
        r = json.loads(r.text)
        msg = r.get("results", [])[0].get("values", {}).get("text", "")
    except Exception as e:
        return False, ""
    return bool(msg), msg


async def proc_message(message):
    cmd = message.get("cmd")
    if cmd == "DANMU_MSG":
        info = message.get("info", {})
        msg = info[1]
        uid = info[2][0]
        user_name = info[2][1]
        ul = info[4][0]
        dl = info[3][0]
        deco = info[3][1]
        print(f"[{uid}] [{user_name}][{ul}] [{deco} {dl}]-> {msg}")

        flag, cuid, cookie = await load_cookie()
        if not flag or uid == cuid:
            return

        flag, msg = await get_tuling_response(msg)
        if flag:
            msg = f"{user_name}　{msg}"[:30]
            await BiliApi.send_danmaku(msg, room_id=MONITOR_ROOM_ID, cookie=cookie)


async def main():
    async def on_connect():
        print("Connected!")

    async def on_shut_down(*args):
        print("dfasfasf")

    async def on_connect(ws):
        print("on_connect")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        print("shut done!")

    async def on_message(message):
        for msg in WsApi.parse_msg(message):
            await proc_message(msg)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,  # "ws://localhost:22222",
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    print("Stated")
    while True:
        await asyncio.sleep(5)


loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(main()))
loop.run_forever()
