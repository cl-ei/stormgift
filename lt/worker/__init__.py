import asyncio


class Worker:

    @classmethod
    async def run(cls):
        await asyncio.sleep(10)

