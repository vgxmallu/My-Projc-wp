from motor.motor_asyncio import AsyncIOMotorClient as _mongo_client_

from config import DB_URL, DB_NAME


mongo = _mongo_client_(DB_URL)
mongodb = mongo[DB_NAME]
