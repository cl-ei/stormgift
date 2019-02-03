import asyncio
import aiohttp


async def main():
    from utils.ws import ReConnectingWsClient
    from utils.biliapi import WsApi

    async def on_connect():
        print("Connected!")

    async def on_shut_down(*args):
        print("dfasfasf")

    async def on_connect(ws):
        print("on_connect")
        await ws.send(WsApi.gen_join_room_pkg(478948))

    async def on_shut_down():
        print("shut done! %s, area: %s" % (4424139, 23))

    async def on_message(*args):
        print(args)

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
loop.run_until_complete(asyncio.gather( main()))
loop.run_forever()
