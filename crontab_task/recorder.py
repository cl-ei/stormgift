#!/usr/bin/env python

import time
import asyncio
import websocket
from multiprocessing import Process, Queue


def process():
    pass


def on_message(ws, message):
    print(message)


def on_error(ws, error):
    print(error)


def on_close(ws):
    print("### closed ###")


def on_open(ws):
    def run():
        while True:
            time.sleep(10)
            ws.send("Heart beat.")
    Thread(target=run, args=(), daemon=True).start()


async def wait_tv_notice(uri):
    ws = websocket.WebSocketApp(
        uri,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )
    print("Run ws ...")

    def run_ws_server():
        ws.run_forever()

    Thread(target=run_ws_server, args=(), daemon=True).start()
    print("Exit.")


async def sync_guard_gift():
    while True:
        await asyncio.sleep(1)
        print(1)


loop = asyncio.get_event_loop()
tasks = [
    asyncio.ensure_future(wait_tv_notice("ws://localhost:8080")),  # 'ws://129.204.43.2:11112'
    asyncio.ensure_future(sync_guard_gift()),
]
loop.run_until_complete(asyncio.wait(tasks))
loop.close()
