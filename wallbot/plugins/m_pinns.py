from pyrogram import Client, filters, enums
from pyrogram.types import Message, ChatPrivileges
#from config import DB_URL
from wallbot import wbot as app
# ================== HELPERS ==================
async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user is admin/owner in the group."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return bool(member.privileges) or member.status == "owner"
    except Exception:
        return False


def admin_only(func):
    """Decorator: restricts command usage to admins/owners."""
    async def wrapper(client: Client, message: Message):
        if not await is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply("⚠️ This command is for admins or creator only.")
        return await func(client, message)
    return wrapper


# ================== COMMANDS ==================
@app.on_message(filters.command("pin") & filters.group)
@admin_only
async def pin_message(client: Client, message: Message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a message to pin it.")

    silent = "silent" in message.text.lower()
    try:
        await message.reply_to_message.pin(disable_notification=silent)
        await message.reply("📌 Message pinned!" + (" (silent)" if silent else ""))
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("unpin") & filters.group)
@admin_only
async def unpin_message(client: Client, message: Message):
    try:
        await client.unpin_chat_message(message.chat.id)
        await message.reply("📍 Unpinned the last pinned message.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("unpinall") & filters.group)
@admin_only
async def unpin_all(client: Client, message: Message):
    try:
        await client.unpin_all_chat_messages(message.chat.id)
        await message.reply("🧹 All pinned messages have been unpinned.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("invitelink") & filters.group)
@admin_only
async def get_invite_link(client: Client, message: Message):
    try:
        link = await client.export_chat_invite_link(message.chat.id)
        await message.reply(f"🔗 **Invite Link:**\n{link}")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("promote") & filters.group)
@admin_only
async def promote_user(client: Client, message: Message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a user to promote them.")

    try:
        await client.promote_chat_member(
            message.chat.id,
            message.reply_to_message.from_user.id,
            privileges=ChatPrivileges(
                can_manage_chat=True,
                can_change_info=True,
                can_delete_messages=True,
                can_manage_video_chats=True,
                can_restrict_members=True,
                can_promote_members=False,
                can_invite_users=True,
                can_pin_messages=True
            )
        )
        await message.reply(f"🛡️ Promoted {message.reply_to_message.from_user.mention} to admin.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@app.on_message(filters.command("demote") & filters.group)
@admin_only
async def demote_user(client: Client, message: Message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a user to demote them.")

    try:
        await client.promote_chat_member(
            message.chat.id,
            message.reply_to_message.from_user.id,
            privileges=ChatPrivileges()  # remove all privileges
        )
        await message.reply(f"⬇️ Demoted {message.reply_to_message.from_user.mention}.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

