import re
import sys
import json
import logging
import traceback


logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


def request(method, url, headers, data=None, params=None, timeout=10):
    import requests
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
    if headers:
        default_headers.update(headers)

    f = requests.post if method.lower() == "post" else requests.get
    try:
        r = f(url=url, headers=default_headers, data=data, params=params, timeout=timeout)
        status_code = r.status_code
        content = r.content.decode("utf-8")
    except Exception as e:
        status_code = 5000
        content = "Error Happened: %s" % e
    return status_code, content


def join_anchor(room_id, gift_id, cookie, gift_type=None):
    csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
    req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v1/Anchor/Join"
    headers = {"Cookie": cookie}
    data = {
        "id": gift_id,
        "platform": "pc",
        "csrf_token": csrf_token,
        "csrf": csrf_token,
        "visit_id": "",
    }
    status_code, content = request(method="post", url=req_url, headers=headers, data=data)
    if status_code != 200:
        return False, "Status code is not 200! content: %s" % content

    try:
        r = json.loads(content)
    except Exception as e:
        return False, "Not json response: %s, content: %s" % (e, content)

    if r.get("code") != 0:
        return False, r.get("msg") or r.get("message")

    return True, f"0_天选时刻"


def join_tv(room_id, gift_id, cookie, gift_type=None):
    csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
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
    status_code, content = request(method="post", url=req_url, headers=headers, data=data)
    if status_code != 200:
        return False, "Status code is not 200! content: %s" % content

    try:
        r = json.loads(content)
    except Exception as e:
        return False, "Not json response: %s, content: %s" % (e, content)

    if r.get("code") != 0:
        return False, r.get("msg", "-")

    return True, f"OK gift_type: {r.get('data', {}).get('type')}"


def join_tv_v5(room_id, gift_id, cookie, gift_type):
    csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
    req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v5/smalltv/join"
    headers = {
        "Cookie": cookie,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://live.bilibili.com",
        "Referer": "https://live.bilibili.com/%s" % room_id,
        "Sec-Fetch-Mode": "cors",
    }
    data = {
        "id": gift_id,
        "roomid": room_id,
        "type": gift_type,
        "csrf_token": csrf_token,
        "csrf": csrf_token,
        "visit_id": ""
    }
    status_code, content = request(method="post", url=req_url, headers=headers, data=data)
    if status_code != 200:
        return False, "Status code is not 200! content: %s" % content

    try:
        r = json.loads(content)
    except Exception as e:
        return False, "Not json response: %s, content: %s" % (e, content)

    if r.get("code") != 0:
        return False, r.get("msg", "-")

    award_name = r["data"]['award_name']
    award_num = r["data"]['award_num']
    return True, f"{award_num}_{award_name}"


def join_guard(room_id, gift_id, cookie, gift_type=None):
    csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
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
    status_code, content = request(method="post", url=req_url, headers=headers, data=data)
    if status_code != 200:
        return False, "Status code is not 200! content: %s" % content

    try:
        r = json.loads(content)
    except Exception as e:
        return False, "Not json response: %s, content: %s" % (e, content)

    if r.get("code") != 0:
        return False, r.get("msg", "-")

    from_user = r["data"]['from']
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
    return True, f"{award_num}_{award_name} <- {from_user}"


def join_pk(room_id, gift_id, cookie, gift_type=None):
    csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
    req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v1/pk/join"
    headers = {"Cookie": cookie}
    data = {
        "roomid": room_id,
        "id": gift_id,
        "csrf_token": csrf_token,
        "csrf": csrf_token,
        "visit_id": ""
    }
    status_code, content = request(method="post", url=req_url, headers=headers, data=data)
    if status_code != 200:
        return False, "Status code is not 200! content: %s" % content

    try:
        r = json.loads(content)
    except Exception as e:
        return False, "Not json response: %s, content: %s" % (e, content)

    if r.get("code") != 0:
        return False, r.get("message")

    award_name = r["data"]['award_text']
    award_num = r["data"]['award_num']
    return True, f"{award_num}_{award_name}"


def join_storm(room_id, gift_id, cookie, gift_type=None):
    csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
    req_url = "https://api.live.bilibili.com/lottery/v1/Storm/join"
    headers = {"Cookie": cookie}
    data = {
        "id": gift_id,
        "color": 16777215,
        "captcha_token": "",
        "captcha_phrase": "",
        "roomid": room_id,
        "csrf_token": csrf_token,
        "csrf": csrf_token,
        "visit_id": "",
    }
    status_code, content = request(method="post", url=req_url, headers=headers, data=data)
    if status_code != 200:
        return False, "Status code is not 200! content: %s" % content

    try:
        r = json.loads(content)
    except Exception as e:
        return False, "Not json response: %s, content: %s" % (e, content)

    if r.get("code") != 0:
        return False, r.get("msg")

    logging.info(f"STORM GIFT R: {r}")

    award_name = "S"  # r["data"]['award_text']
    award_num = 1  # r["data"]['award_num']
    return True, f"{award_num}_{award_name}"


def accept_handler(q, act, room_id, gift_id, cookie, gift_type=None):
    if act == "join_tv":
        f = join_tv
    elif act == "join_tv_v5":
        f = join_tv_v5
    elif act == "join_guard":
        f = join_guard
    elif act == "join_pk":
        f = join_pk
    elif act == "join_storm":
        f = join_storm
    elif act == "join_anchor":
        f = join_anchor
    else:
        q.put(None)
        return

    result = f(room_id=room_id, gift_id=gift_id, cookie=cookie, gift_type=gift_type)
    q.put(result)


def main_handler(event, context):
    try:
        request_params = json.loads(event["body"])
        if not request_params:
            raise ValueError("Bad request_params: `%s`." % request_params)

        act = request_params["act"]
        room_id = request_params["room_id"]
        gift_id = request_params["gift_id"]
        cookies = request_params["cookies"]
        gift_type = request_params.get("gift_type", "")

        assert isinstance(cookies, list) and len(cookies) > 0
    except Exception as e:
        return {
            "headers": {"Content-Type": "text"},
            "statusCode": 403,
            "body": "Request Param Error: %s\n\n%s" % (e, traceback.format_exc())
        }

    from threading import Thread
    from queue import Queue

    count = len(cookies)
    queues = [Queue(maxsize=1) for _ in range(count)]

    threads = [
        Thread(target=accept_handler, args=(queues[_], act, room_id, gift_id, cookies[_], gift_type))
        for _ in range(count)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = [q.get_nowait() for q in queues]
    logging.info("Request result: %s" % result)

    return {
        "headers": {"Content-Type": "text"},
        "statusCode": 200,
        "body": json.dumps(result, ensure_ascii=False)
    }
