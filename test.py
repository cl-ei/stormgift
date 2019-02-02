import asyncio
import aiohttp


def create_task(c):
    return asyncio.get_event_loop().create_task(c)


async def create_client():
    ws_session = aiohttp.ClientSession()
    async with ws_session.ws_connect(url='ws://localhost:8765') as ws:
        async def send_heart_beat():
            while not ws.closed:
                print("send heart beat")
                try:
                    await ws.send_str("heart beat")
                except Exception as e:
                    print("e: %s" % e)
                    return
                await asyncio.sleep(10)

        task = create_task(send_heart_beat())
        async for msg in ws:
            print("r: %s" % msg.type)
        await task

    await ws_session.close()


async def manager():
    while True:
        tasks = asyncio.all_tasks()
        for _ in tasks:
            print(_)
        await asyncio.sleep(2)


loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(create_client()))
loop.run_forever()
