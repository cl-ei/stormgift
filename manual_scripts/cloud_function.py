# -*- coding: utf-8 -*-
import sys
import json
import logging
import requests
import traceback

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


def main_handler(event, context):

    try:
        request_params = json.loads(event["body"])
        if not request_params:
            raise ValueError("Bad request_params: `%s`." % request_params)

        method = request_params["method"].lower()
        url = request_params["url"]
        headers = request_params["headers"]
        timeout = request_params["timeout"]
        data = request_params.get("data", {})
        params = request_params.get("params", {})

    except Exception as e:
        return {
            "headers": {"Content-Type": "text"},
            "statusCode": 403,
            "body": "Request Param Error: %s\n\n%s" % (e, traceback.format_exc())
        }

    if method == "post":
        r = requests.post(url=url, data=data, headers=headers, timeout=timeout)
    else:
        r = requests.get(url=url, params=params, headers=headers, timeout=timeout)

    return {
        "headers": {"Content-Type": "text"},
        "statusCode": r.status_code,
        "body": r.content.decode("utf-8")
    }
