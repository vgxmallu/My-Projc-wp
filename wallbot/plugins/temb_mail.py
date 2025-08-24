from pyrogram import Client, filters
import requests as re
from wallbot import wbot as app
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os

buttons = InlineKeyboardMarkup([
    [InlineKeyboardButton('Generate', callback_data='generate'),
     InlineKeyboardButton('Refresh', callback_data='refresh'),
     InlineKeyboardButton('Close', callback_data='close')]
])

msg_buttons = InlineKeyboardMarkup([
    [InlineKeyboardButton('View message', callback_data='view_msg'),
     InlineKeyboardButton('Close', callback_data='close')]
])

# Store email and idnum per chat
user_data = {}

@app.on_message(filters.command('tembmail'))
async def start_msgsd(client, message):
    chat_id = message.chat.id
    user_data[chat_id] = {'email': '', 'idnum': ''}
    await message.reply(
        "**Hey❕**\nThis bot generates temporary emails that self-destruct after a certain time.\n\n"
        "**__How It Safe's You?__**\n- Using temporary mail protects your real mailbox and personal info.",
        reply_markup=buttons
    )

@app.on_callback_query(filters.regex("generate"))
async def generate_email(client, callback_query):
    chat_id = callback_query.message.chat.id
    email = re.get("https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1").json()[0]
    user_data[chat_id]['email'] = email
    await callback_query.edit_message_text(
        f'__**Your Temporary E-mail:**__ `{email}`', reply_markup=buttons
    )

@app.on_callback_query(filters.regex("refresh"))
async def refresh_mailbox(client, callback_query):
    chat_id = callback_query.message.chat.id
    email = user_data.get(chat_id, {}).get('email', '')
    if not email:
        await callback_query.edit_message_text('Generate an email first.', reply_markup=buttons)
        return
    getmsg_url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={email.split('@')[0]}&domain={email.split('@')[1]}"
    ref_response = re.get(getmsg_url).json()
    if not ref_response:
        await callback_query.answer('No messages received in your mailbox.', show_alert=True)
        return
    user_data[chat_id]['idnum'] = str(ref_response[0]['id'])
    from_msg = ref_response[0]['from']
    subject = ref_response[0]['subject']
    refreshrply = f'You have a message from {from_msg}\n\nSubject: {subject}'
    await callback_query.edit_message_text(refreshrply, reply_markup=msg_buttons)

@app.on_callback_query(filters.regex("view_msg"))
async def view_message(client, callback_query):
    chat_id = callback_query.message.chat.id
    email = user_data.get(chat_id, {}).get('email', '')
    idnum = user_data.get(chat_id, {}).get('idnum', '')
    if not email or not idnum:
        await callback_query.answer('No email or message ID found.', show_alert=True)
        return
    msg_url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={email.split('@')[0]}&domain={email.split('@')[1]}&id={idnum}"
    msg = re.get(msg_url).json()
    from_mail = msg.get('from', '')
    date = msg.get('date', '')
    subjectt = msg.get('subject', '')
    body = msg.get('body', '')
    attachments = msg.get('attachments', [])
    mailbox_view = (f'ID No: {idnum}\nFrom: {from_mail}\nDate: {date}\n'
                    f'Subject: {subjectt}\nMessage:\n{body}')
    if not attachments:
        await callback_query.edit_message_text(mailbox_view, reply_markup=buttons)
        await callback_query.answer("No attachments found.", show_alert=True)
    else:
        dlattach = attachments[0]['filename']
        attc = (f"https://www.1secmail.com/api/v1/?action=download&login={email.split('@')[0]}"
                f"&domain={email.split('@')[1]}&id={idnum}&file={dlattach}")
        mailbox_vieww = f'{mailbox_view}\n\n[Download]({attc}) Attachments'
        await callback_query.edit_message_text(mailbox_vieww, reply_markup=buttons)

@app.on_callback_query(filters.regex("close"))
async def close_query(client, callback_query):
    await callback_query.message.delete()
