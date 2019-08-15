# -*- coding: utf-8 -*-
import sys
import json
import logging
import requests

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


def main_handler(event, context):
    url = "https://www.madliar.com/log"
    r = requests.get(url=url, params={"event": event, "context": context})

    response = {
        "result": r.status_code == 200,
        "data": r.content,
    }

    return {
        "headers": {
            "Content-Type": "text",
            "Access-Control-Allow-Origin": "*"
        },
        "statusCode": 200,
        "body": json.dumps(response)
    }
