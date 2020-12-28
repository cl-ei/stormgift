import os
import asyncio
from typing import *
from random import choice
from src.db.clients.mongo import db
from src.db.models.images import ImageDoc


def get_file_name_list(path: str) -> List[str]:
    """ 递归获取该目录下面的所有文件路径 """
    files = os.listdir(path)
    result = []
    for file_name in files:
        file_loc = os.path.join(path, file_name)
        if os.path.isfile(file_loc):
            result.append(file_loc)
        elif os.path.isdir(file_loc):
            result.extend(get_file_name_list(file_loc))
    return result


async def main():
    search_path = "/data/IMAGE"
    files = get_file_name_list(search_path)
    while files:
        path = choice(files)
        doc = ImageDoc(path=path)
        await doc.save(db)
        files.remove(path)
    print(f"Done!")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
