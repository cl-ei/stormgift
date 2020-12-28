from src.db.clients.mongo import RWModel, ReturnDocument, db


class ImageDoc(RWModel):
    __collection__ = "image"

    path: str


class UsedRecDoc(RWModel):
    name: str
    seq: int = 0


async def get_image(name: str) -> str:
    assert name in ("yk", "zy")

    collection = db[UsedRecDoc.__collection__]
    result = await collection.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        projection={'seq': True, '_id': True},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    this_id = result["seq"]
    image = await ImageDoc.get_by_id(db, this_id)
    if image:
        return image.path

    await collection.find_one_and_update(
        {'_id': name},
        {'$set': {"seq": 0}},
        upsert=True
    )
    image = await image.get_by_id(db, 0)
    return image.path if image else ""
