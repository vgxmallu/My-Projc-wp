from pyrogram import Client, filters
from pyrogram.types import Message
from config import LOG_CHANNEL

# Function to handle feedback and bug reporting
@Client.on_message(filters.command(["bug", "bugs", "feedback"]))
async def bug_handler(client: Client, message: Message):
    try:
        # Check if the command has additional arguments or a reply to a message
        if len(message.command) < 2:
            if message.reply_to_message and message.reply_to_message.text:
                bug_report = message.reply_to_message.text.strip()
            else:
                return await message.reply_text(
                    "Please reply to a text message or provide a description of the bug."
                )
        else:
            bug_report = message.text.split(" ", 1)[1].strip()

        # Check for empty bug reports
        if not bug_report:
            return await message.reply_text("The bug description cannot be empty. Please try again.")

        # Construct the acknowledgment message
        response_message = (
            f"Hi {message.from_user.mention},\n"
            "Thank you for reporting the issue. It has been forwarded to the developer."
        )
        await message.reply_text(response_message)

        # Log the bug report to the designated channel
        log_message = (
            f"#BugReport\n\n"
            f"**User:** {message.from_user.mention} ([User ID: {message.from_user.id}])\n"
            f"**Chat:** {message.chat.title if message.chat.type != 'private' else 'Private Chat'}\n"
            f"**Chat ID:** {message.chat.id}\n"
            f"**Bug Description:**\n{bug_report}"
        )
        await client.send_message(LOG_CHANNEL, text=log_message)

    except Exception as e:
        # Error handling and reporting to developers
        await message.reply_text(
            "An unexpected error occurred while processing your request. Please try again later."
        )
        error_message = (
            f"#Error\n\n"
            f"**Error occurred in bug handler:**\n{str(e)}\n\n"
            f"**User:** {message.from_user.mention} ([User ID: {message.from_user.id}])\n"
            f"**Chat ID:** {message.chat.id}"
        )
        await client.send_message(LOG_CHANNEL, text=error_message)
