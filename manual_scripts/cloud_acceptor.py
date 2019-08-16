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
        headers.update(default_headers)
    else:
        headers = default_headers

    f = requests.post if method.lower() == "post" else requests.get
    try:
        r = f(url=url, headers=headers, data=data, params=params, timeout=timeout)
        status_code = r.status_code
        content = r.content.decode("utf-8")
    except Exception as e:
        status_code = 5000
        content = "Error Happened: %s" % e
    return status_code, content


def join_tv(room_id, gift_id, cookie):
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


def join_guard(room_id, gift_id, cookie):
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

    message = r.get("data", {}).get('message')
    from_user = r.get("data", {}).get('from')
    return True, "%s, from %s" % (message, from_user)


def join_pk(room_id, gift_id, cookie):
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

    return True, r.get("data", {}).get("title", "unknown tittle")


def accept_handler(q, act, room_id, gift_id, cookie):
    if act == "join_tv":
        f = join_tv
    elif act == "join_guard":
        f = join_guard
    elif act == "join_pk":
        f = join_pk
    else:
        q.put(None)
        return

    result = f(room_id=room_id, gift_id=gift_id, cookie=cookie)
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
        Thread(target=accept_handler, args=(queues[_], act, room_id, gift_id, cookies[_]))
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