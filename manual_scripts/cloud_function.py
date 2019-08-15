# -*- coding: utf-8 -*-
import sys
import json
import logging
import requests

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


def main_handler(event, context):

    try:
        request_params = json.loads(event["body"])
        if not request_params:
            raise ValueError("Bad request_params: `%s`." % request_params)
    except Exception as e:
        return {
            "headers": {"Content-Type": "text"},
            "statusCode": 403,
            "body": "Request Param Error: %s" % e
        }

    url = "https://www.madliar.com/log"
    r = requests.post(url=url, params={"msg": json.dumps(request_params)})

    response = {
        "result": r.status_code == 200,
        "data": r.content,
    }

    return {
        "headers": {"Content-Type": "application/json"},
        "statusCode": 200,
        "body": json.dumps(response)
    }
