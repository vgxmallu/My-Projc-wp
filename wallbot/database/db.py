from wallbot import collection, user_Collection

async def add_user(user_id, username, first_name):
    user = {
        "id": user_id,
        "username": username,
        "first_name": first_name
    }
    await collection.insert_one(user)

async def get_user(user_id):
    user = await collection.find_one({"id": user_id})
    return user

async def add_group(group_id, group_name):
    group = {
        "id": group_id,
        "name": group_name
    }
    await user_Collection.insert_one(group)

async def get_group(group_id):
    group = await user_Collection.find_one({"id": group_id})
    return group


async def update_stats(user_id: int, field: str, value: int):
    await user_Collection.update_one(
        {"id": user_id},
        {"$inc": {field: value}},
        upsert=True
    )

async def get_stats(user_id: int):
    stats = await user_Collection.find_one({"id": user_id})
    return stats or {
        "games_played": 0,
        "games_won": 0,
        "total_words": 0,
        "total_letters": 0,
        "longest_word": "None"
    }

async def update_longest_word(user_id: int, word: str):
    current = await user_Collection.find_one({"id": user_id})
    if not current or len(word) > len(current.get("longest_word", "")):
        await user_Collection.update_one(
            {"id": user_id},
            {"$set": {"longest_word": word}},
            upsert=True
        )
