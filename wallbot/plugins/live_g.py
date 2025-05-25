from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID  # OWNER.ID is used

# Forward user messages to owner
@Client.on_message(filters.private & ~filters.user(OWNER_ID))
async def forward_to_owner(client: Client, message: Message):
    try:
        await message.forward(OWNER_ID)
    except Exception as e:
        print(f"[Forward Error] {e}")

# Owner replies to forwarded message
@Client.on_message(filters.private & filters.user(OWNER_ID))
async def reply_to_user(client: Client, message: Message):
    if message.reply_to_message:
        original_sender = message.reply_to_message.forward_from
        if original_sender:
            try:
                await client.send_message(chat_id=original_sender.id, text=message.text)
            except Exception as e:
                await message.reply(f"❌ Failed to send message: {e}")
        else:
            await message.reply("⚠️ Can't find original sender.")
    else:
        await message.reply("🔁 Please reply to a forwarded message.")
