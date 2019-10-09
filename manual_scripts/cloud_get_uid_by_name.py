# -*- coding: utf-8 -*-
import re
import sys
import json
import logging
import traceback

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


def request(method, url, data=None, params=None, headers=None):
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
    try:
        if method.lower() == "get":
            r = requests.get(url=url, headers=default_headers, params=params, timeout=2)
        else:
            r = requests.post(url=url, headers=default_headers, data=data, timeout=2)
        status_code = r.status_code
        content = r.content.decode("utf-8")
    except Exception as e:
        status_code = 500
        content = f"Error in request: {e}"

    return status_code, content


def get_user_id_by_search_way(user_name):
    req_url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {
        "search_type": "bili_user",
        "keyword": user_name,
    }
    code, content = request("get", url=req_url, params=params)
    if code != 200:
        return False, content

    try:
        r = json.loads(content)
    except json.JSONDecodeError:
        return False, f"Response: json.JSONDecodeError: {content}"

    if r["code"] != 0:
        return False, r.get("message") or r.get("msg")

    result_list = r.get("data", {}).get("result", []) or []
    if not result_list:
        return False, "No result."

    uid = None
    for r in result_list:
        if r.get("uname") == user_name:
            uid = int(r.get("mid", 0)) or None
            break
    return bool(uid), uid


def add_admin(user_name, cookie):
    try:
        anchor_id = re.findall(r"DedeUserID=(\d+)", cookie)[0]
        csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
    except (IndexError, ValueError, TypeError):
        return False, f"Bad cookie! {cookie}"

    req_url = "https://api.live.bilibili.com/live_user/v1/RoomAdmin/add"
    headers = {"Cookie": cookie}
    data = {
        "admin": user_name,
        "anchor_id": anchor_id,
        "csrf_token": csrf_token,
        "csrf": csrf_token,
        "visit_id": ""
    }
    code, content = request("post", url=req_url, headers=headers, data=data)
    if code != 200:
        return False, content

    try:
        r = json.loads(content)
    except json.JSONDecodeError:
        return False, f"response: json.JSONDecodeError: {content}"

    return r["code"] in (0, 1008021), r.get("msg") or r.get("message")


def remove_admin(uid, cookie):
    try:
        csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
    except (IndexError, ValueError, TypeError):
        return False, "Bad cookie."

    req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/dismiss"
    headers = {"Cookie": cookie}
    data = {
        "uid": uid,
        "csrf_token": csrf_token,
        "csrf": csrf_token,
        "visit_id": ""
    }
    code, content = request("post", url=req_url, headers=headers, data=data)
    if code != 200:
        return False, content

    try:
        r = json.loads(content)
    except json.JSONDecodeError:
        return False, f"response: json.JSONDecodeError: {content}"

    return r["code"] in (0, 1008023), r.get("msg") or r.get("message")


def get_admin_list(cookie):
    req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/get_by_anchor"
    headers = {"Cookie": cookie}
    params = {"page": 1}

    result = []
    error_message = []
    for _ in range(5):
        code, content = request("get", url=req_url, params=params, headers=headers)
        if code != 200:
            error_message.append(f"http code != 200, content: {content}")
            continue

        try:
            r = json.loads(content)
        except json.JSONDecodeError:
            error_message.append(f"json.JSONDecodeError, content: {content}")
            continue

        if r["code"] not in (0, ):
            error_message.append(r.get("msg") or r.get("message"))
            continue

        admin_list = r.get("data", {}).get("data", []) or []
        result.extend(admin_list)

        total_page = r["data"]["page"]["total_page"]
        if params["page"] < total_page:
            params["page"] += 1
        else:
            break

    return bool(result), result or "\n".join(error_message)


def main_handler(event, context):
    try:
        request_params = json.loads(event["body"])
        if not request_params:
            raise ValueError("Bad request_params: `%s`." % request_params)

        cookie = request_params["cookie"]
        name = request_params["name"]

    except Exception as e:
        return {
            "headers": {"Content-Type": "text"},
            "statusCode": 403,
            "body": "Request Param Error: %s\n\n%s" % (e, traceback.format_exc())
        }

    logger.info(f"Search user: {name}, cookie:\n\t{cookie}")
    flag, data = get_user_id_by_search_way(user_name=name)
    if flag:
        response = [True, data]
        return {"headers": {"Content-Type": "text"}, "statusCode": 200, "body": json.dumps(response)}

    logging.warning(f"Cannot get user name by search way.")

    flag, message = add_admin(user_name=name, cookie=cookie)
    if not flag:
        response = [False, message]
        return {"headers": {"Content-Type": "text"}, "statusCode": 200, "body": json.dumps(response)}

    flag, admin_list = get_admin_list(cookie=cookie)
    if not flag:
        response = [False, message]
        return {"headers": {"Content-Type": "text"}, "statusCode": 200, "body": json.dumps(response)}

    user_id = None
    for admin in admin_list:
        if admin["uname"] == name and user_id is None:
            user_id = admin["uid"]
            remove_admin(user_id, cookie=cookie)
        elif admin["uname"] == "":
            remove_admin(admin["uid"], cookie=cookie)

    response = [bool(user_id), user_id]
    return {"headers": {"Content-Type": "text"}, "statusCode": 200, "body": json.dumps(response)}


if __name__ == "__main__":
    event = {
        "body": json.dumps({
            "cookie": "",
            "name": "你的"
        })
    }

    r = main_handler(event, {})
    print(r)
