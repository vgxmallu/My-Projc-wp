import uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pymongo import MongoClient
from datetime import datetime, timedelta
from config import DB_URL
from wallbot import wbot as app
DB_NAME = "whisper_db"
EXPIRE_MINUTES = 30  # whispers auto-delete after 30 minutes
# ----------------------------------------


mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
whispers_col = db["whispers"]

# ---------------- HELPERS ----------------
def make_whisper(sender_id, receiver_id, text):
    whisper_id = str(uuid.uuid4())
    whispers_col.insert_one({
        "_id": whisper_id,
        "sender": sender_id,
        "receiver": receiver_id,
        "text": text,
        "created": datetime.utcnow(),
        "seen": False
    })
    return whisper_id

def get_whisper(whisper_id, user_id):
    whisper = whispers_col.find_one({"_id": whisper_id})
    if not whisper:
        return None, "❌ Whisper expired or invalid!"
    if whisper["receiver"] != user_id and whisper["sender"] != user_id:
        return None, "❌ This whisper is not for you!"
    if datetime.utcnow() - whisper["created"] > timedelta(minutes=EXPIRE_MINUTES):
        whispers_col.delete_one({"_id": whisper_id})
        return None, "⌛ Whisper expired!"
    if not whisper["seen"] and user_id == whisper["receiver"]:
        whispers_col.update_one({"_id": whisper_id}, {"$set": {"seen": True}})
    return whisper, None

# ---------------- COMMAND ----------------
@app.on_message(filters.command("whisper"))
async def whisper_cmd(_, msg: Message):
    if not msg.reply_to_message or len(msg.command) < 2:
        return await msg.reply("Usage:\nReply to someone → `/whisper your secret text`")
    
    receiver = msg.reply_to_message.from_user
    sender = msg.from_user
    text = " ".join(msg.command[1:])
    
    whisper_id = make_whisper(sender.id, receiver.id, text)
    
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔒 View Whisper", callback_data=f"whisper_{whisper_id}")
    ]])
    
    await msg.reply(
        f"🤫 {sender.mention} sent a secret whisper to {receiver.mention}!",
        reply_markup=buttons
    )

# ---------------- CALLBACK ----------------
@app.on_callback_query(filters.regex(r"^whisper_(.*)"))
async def whisper_cb(_, cq: CallbackQuery):
    whisper_id = cq.data.split("_", 1)[1]
    whisper, error = get_whisper(whisper_id, cq.from_user.id)
    
    if error:
        return await cq.answer(error, show_alert=True)
    
    sender = whisper["sender"]
    text = whisper["text"]
    seen = whisper["seen"]
    
    if cq.from_user.id == whisper["receiver"]:
        await cq.answer(f"📩 Whisper from {sender}: {text}", show_alert=True)
    elif cq.from_user.id == whisper["sender"]:
        status = "✅ Seen" if seen else "⌛ Not seen yet"
        await cq.answer(f"📤 Your whisper to receiver\n\nText: {text}\nStatus: {status}", show_alert=True)

