from pyrogram import Client, filters, enums
from pyrogram.enums import ChatAction
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import time
import Script
import requests
import config
import html
import json
import asyncio
from funcs import *
import uuid
import os
from datetime import datetime
from gtts import gTTS
import math
#from plugins.newton import math_request

headers = {"User-Agent": "Mozilla/5.0"}

link_dict = {}

import json
import urllib.parse
import urllib.request

BASE_URL = 'https://newton.vercel.app/api/v2/'

def math_request(operation: str, expression: str):
    """
    Sends a request to Newton API v2 with given operation and expression.
    
    :param operation: One of the supported operations like 'simplify', 'derive'
    :param expression: The math expression as a string
    :return: Result from the API or error message
    """
    url = f"{BASE_URL}{operation}/{urllib.parse.quote(expression)}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())

            # Return the 'result' field
            return data.get("result", "No result found.")
    except Exception as e:
        return f"Error: {e}"

#ping
@Client.on_message(filters.command('ping') & filters.incoming)
async def ping(client, message):
                start_time = time.time()
                m = await message.reply('Pinging....', quote=True)
                end_time = time.time()
                elapsed_time = (end_time - start_time) * 1000
                await m.edit(f'Pong!\n{elapsed_time:.3f}ms')
                
#start
#@Client.on_message(filters.command('start'))
async def fffstart(client, message):
    if len(message.command) > 1 and message.command[1].startswith("upload_"):
        k = await message.reply("Fetching Download link...")
        key = message.command[1][7:]
        link = link_dict.get(key)
        try:
            resp = requests.get(link, headers=headers, timeout=10)
            soup = bs4.BeautifulSoup(resp.text, 'html.parser')
            dl_btn = soup.select_one("a#download-button")
            if dl_btn:
                real_url = dl_btn.get("data-downloadurl")
            else:
                await k.edit("Download link not found.")
        except Exception as e:
            await k.edit(f"Error fetching download link: {e}")
        try:
            await k.edit("Downloading file...")
            response = requests.get(real_url, stream=True, headers=headers, timeout=10)
            filename = await sanitize_filename(await get_filename_from_cd(response) or f"file_{key}.srt")
            await k.edit(f"Uploading: <code>{filename}</code>")
            with open(filename, "wb") as f:
                f.write(response.content)

            await client.send_document(
                chat_id=message.from_user.id,
                document=filename,
                caption=f"📁 Filename : <code>{filename}</code>",
                parse_mode=enums.ParseMode.HTML
            )
            time.sleep(2)
            await k.delete()
        except Exception as e:
            await k.edit(f"Failed to upload the file.\n {e}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)  # clean up
    else:
        thunder = await message.reply('⚡')
        await asyncio.sleep(1)
        await thunder.delete()
        button = [
        [InlineKeyboardButton('📣My Channel', url='t.me/xbots_x')]]
        reply_markup = InlineKeyboardMarkup(button)
        await message.reply(Script.START_TEXT, reply_markup=reply_markup, quote=True, parse_mode=enums.ParseMode.HTML)
                
 
#id filter               
#@Client.on_message(filters.command('id') & filters.incoming)
async def whois(client, message):
                message = message.reply_to_message or message
                first = message.from_user.first_name
                last = message.from_user.last_name
                id = message.from_user.id
                username = message.from_user.username
                dc = message.chat.dc_id
                chatid = message.chat.id
                button = [
                            [InlineKeyboardButton('❌ Close', callback_data='close')]
                        ]
                reply_markup = InlineKeyboardMarkup(button)
                await message.reply_text(Script.ID_TEXT.format(first, last, username, id, dc, chatid), reply_markup=reply_markup)

@Client.on_message(filters.command('echo') & filters.text)
async def echofunc(client, message):
    if message.reply_to_message:
        # Replied message, use its text
        cmd = message.reply_to_message.text or message.reply_to_message.caption or ""

    elif len(message.text.split(' ', 1)) > 1:
        # Command has argument like /echo something
        cmd = message.text.split(' ', 1)[1]

    else:
        # No reply and no extra text
        return await message.reply(
            "<b>Example:</b>\n<code>/echo Who are you?</code>",
            parse_mode=enums.ParseMode.HTML
        )

    if len(cmd) > 4096:
        return await message.reply("Message too long! Please keep it under 4096 characters.")

    await client.send_message(
        chat_id=message.chat.id,
        text=cmd,
        reply_to_message_id= message.reply_to_message.id if message.reply_to_message else message.id,
        disable_web_page_preview=True,
    )

def extract_expression(message):
    return message.text.split(' ', 1)[1] if len(message.command) >= 2 else None


@Client.on_message(filters.command('simplify') & filters.text)
async def simplify(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/simplify 2^2+2(2)</code>')
    await message.reply_text(math_request("simplify", expr))


@Client.on_message(filters.command('factor') & filters.text)
async def factor(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/factor x^2 + 2x</code>')
    await message.reply_text(math_request("factor", expr))


@Client.on_message(filters.command('derive') & filters.text)
async def derive(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/derive x^2+2x</code>')
    await message.reply_text(math_request("derive", expr))


@Client.on_message(filters.command('integrate') & filters.text)
async def integrate(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/integrate x^2+2x</code>')
    await message.reply_text(math_request("integrate", expr))


@Client.on_message(filters.command('zeroes') & filters.text)
async def zeroes(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/zeroes x^2+2x</code>')
    await message.reply_text(math_request("zeroes", expr))


@Client.on_message(filters.command('tangent') & filters.text)
async def tangent(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/tangent 2|x^3</code>\nWhere 2 is the x value at which you want to find the tangent line, and x^3 is the function expression.')
    await message.reply_text(math_request("tangent", expr))


@Client.on_message(filters.command('area') & filters.text)
async def area(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/area 2:4|x^3</code>\nWhere 2 is the starting x value, 4 is the ending x value, and x^3 is the function under which you want the area between the two x values.')
    await message.reply_text(math_request("area", expr))


@Client.on_message(filters.command('cos') & filters.text)
async def cos(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/cos pi</code>')
    await message.reply_text(math.cos(eval(expr)))


@Client.on_message(filters.command('sin') & filters.text)
async def sin(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/sin 0</code>')
    await message.reply_text(math.sin(eval(expr)))


@Client.on_message(filters.command('tan') & filters.text)
async def tan(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/tan 0</code>')
    await message.reply_text(math.tan(eval(expr)))


@Client.on_message(filters.command('arccos') & filters.text)
async def arccos(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/arccos 1</code>')
    await message.reply_text(math.acos(eval(expr)))


@Client.on_message(filters.command('arcsin') & filters.text)
async def arcsin(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/arcsin 0</code>')
    await message.reply_text(math.asin(eval(expr)))


@Client.on_message(filters.command('arctan') & filters.text)
async def arctan(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/arctan 0</code>')
    await message.reply_text(math.atan(eval(expr)))


@Client.on_message(filters.command('abs') & filters.text)
async def abs_(bot, message):  # `abs` is a Python built-in, renamed to abs_
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/abs -1</code>')
    await message.reply_text(math.fabs(eval(expr)))


@Client.on_message(filters.command('log') & filters.text)
async def log(bot, message):
    expr = extract_expression(message)
    if not expr:
        return await message.reply('<b>Example:</b>\n<code>/log 10</code>')
    await message.reply_text(math.log(eval(expr)))


@Client.on_message(filters.command('blockanimation') & filters.incoming)
async def blockanimation(bot, message):
    msg = await bot.send_message(
        chat_id=message.chat.id,
        text="⬜",
        reply_to_message_id= message.reply_to_message.id if message.reply_to_message else message.id,
        disable_web_page_preview=True,
    )
    for x in range(18):
        await msg.edit(Script.block_chain[x%18])
        time.sleep(1)
    await msg.edit('🟥')

@Client.on_message(filters.command('bombs') & filters.incoming)
async def bombs(bot, update):
    msg = await bot.send_message(
        chat_id=update.chat.id,
        text="💣",
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    for x in range(9):
        await msg.edit(Script.bomb_ettu[x%9])
        time.sleep(1)
    await msg.edit('RIP PLOX...')
    
@Client.on_message(filters.command('police') & filters.incoming)
async def police(bot, update):
    msg = await bot.send_message(
        chat_id=update.chat.id,
        text="Police is coming!",
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    for x in range(3):
        await msg.edit(Script.police_siren[x%2])
        time.sleep(1)
    await msg.edit('Police is here!')
@Client.on_message(filters.command('hack') & filters.text)
async def hack(bot, update):
    if len(update.command) < 2:
        return await update.reply('<b>Example:</b>\n<code>/hack @JamesW</code>', )
    cmd = update.text.split(' ', 1)[1]
    msg = await bot.send_message(
        chat_id=update.chat.id,
        text=f'Target {cmd} selected',
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    for x in range(10):
        await msg.edit_text(Script.hack_you[x%5])
        time.sleep(1)
    await msg.edit(f'Successfully hacked {cmd}\'s all data and sent to Admin\'s Database.')


@Client.on_message(filters.command('love') & filters.incoming)
async def love(bot, update):
    msg = await bot.send_message(
        chat_id=update.chat.id,
        text='❣️',
        reply_to_message_id= update.reply_to_message.id if update.reply_to_message else update.id,
        disable_web_page_preview=True,
    )
    for x in range(10):
        await msg.edit(Script.love_siren[x%5])
        time.sleep(1)
    await msg.edit('True Love💞')

@Client.on_message(filters.command('msone') & filters.incoming)
async def msone(bot, message):
    if len(message.command) < 2:
        return await message.reply('<b>Example:</b>\n<code>/msone Titanic</code>')

    res = await message.reply('Searching...', quote=True)
    cmd = message.text.split(' ', 1)[1]
    buttons = []
    download_links = []

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://google.com"
    }

    titles = await msonescrap(cmd, 'title')
    links = await msonescrap(cmd, 'link')
    me = await bot.get_me()
    if titles == 'Nothing' or links == 'Nothing':
        return await res.edit('No results found.')
    # Build buttons for available links
    for title, link in zip(titles, links):
        if link:
            key = str(uuid.uuid4())[:8]
            link_dict[key] = link
            buttons.append([InlineKeyboardButton(title, url=f"https://t.me/{me.username}?start=upload_{key}")])

    buttons.append([InlineKeyboardButton('❌ CLOSE', callback_data='close_data')])
    markup = InlineKeyboardMarkup(buttons)

    await res.edit(f'Here is your result for your query <b>{cmd}</b>', reply_markup=markup)

@Client.on_message(filters.command('github') & filters.text)        
async def github(bot, message):
    if len(message.command) < 2:
        return await message.reply('<b>Example:</b>\n<code>/github torvalds</code>')
    
    res = await message.reply('Searching...', quote=True)
    username = message.text.split(' ', 1)[1]
    headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://google.com"
}
    usr = requests.get(f'https://api.github.com/users/{username}', headers=headers).json()
    if usr.get('login'):
        reply_text = f"""<b>Name:</b> <code>{usr.get('name') or 'N/A'}</code>
<b>Username:</b> <code>{usr['login']}</code>
<b>Account ID:</b> <code>{usr['id']}</code>
<b>Account type:</b> <code>{usr['type']}</code>
<b>Site Admin:</b> <code>{usr.get('site_admin', False)}</code>
<b>User View Type:</b> <code>{usr.get('user_view_type', 'N/A')}</code>
<b>Location:</b> <code>{usr.get('location') or 'N/A'}</code>
<b>Bio:</b> <code>{usr.get('bio') or 'N/A'}</code>
<b>Followers:</b> <code>{usr.get('followers')}</code>
<b>Following:</b> <code>{usr.get('following')}</code>
<b>Hireable:</b> <code>{usr.get('hireable') or 'N/A'}</code>
<b>Public Repos:</b> <code>{usr.get('public_repos')}</code>
<b>Public Gists:</b> <code>{usr.get('public_gists')}</code>
<b>Email:</b> <code>{usr.get('email') or 'N/A'}</code>
<b>Company:</b> <code>{usr.get('company') or 'N/A'}</code>
<b>Twitter:</b> <code>{usr.get('twitter_username') or 'N/A'}</code>
<b>Website:</b> <code>{usr.get('blog') or 'N/A'}</code>
<b>Avatar URL:</b> <a href="{usr.get('avatar_url')}">Link</a>
<b>Profile URL:</b> <a href="{usr['html_url']}">GitHub</a>
<b>Last Updated:</b> <code>{usr.get('updated_at')}</code>
<b>Account Created At:</b> <code>{usr.get('created_at')}</code>
"""
    else:
        reply_text = "User not found. Make sure you entered valid username!"
    await message.reply_photo(usr.get('avatar_url'), caption=reply_text, parse_mode=enums.ParseMode.HTML)
    await res.delete()

@Client.on_message(filters.command('lyrics') & filters.text)   
async def lyrics(bot, update):
    if len(update.command) < 2:
        return await update.reply('<b>Example:</b>\n<code>/lyrics Middle of the night</code>')
    query = update.text.split(' ', 1)[1]
    k = await update.reply(f'Searching for {query}...', parse_mode=enums.ParseMode.HTML)
    
    headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://google.com"
}

    res = requests.get(f'https://lrclib.net//api/search?q={html.escape(query)}', headers=headers)
    try:
        lyric = json.loads(res.text)[0]['plainLyrics']
    except (json.JSONDecodeError, IndexError):
        lyric = None
    if lyric:
        await k.edit(f'📝 Lyrics for <b>{query}</b>:\n\n<pre>{lyric}</pre>', parse_mode=enums.ParseMode.HTML)
    else:
        await k.edit('No lyrics found for this song.')
@Client.on_message(filters.command('gifid') & filters.incoming)    
async def gifid(bot, update):
    if update.reply_to_message and update.reply_to_message.animation:
        await update.reply_text(f"Gif ID:\n<code>{update.reply_to_message.animation.file_id}</code>",
                                            parse_mode=enums.ParseMode.HTML)
    else:
        await update.reply_text("<i>Please reply to a gif to get its ID.</i>", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command('speedtest') & filters.incoming)
async def speedtestxyz(bot, update):
    buttons = [
        [InlineKeyboardButton("Image", callback_data="speedtest_image"), InlineKeyboardButton("Text", callback_data="speedtest_text")]
    ]
    await update.reply_text("Select SpeedTest Mode", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_message(filters.command('stickerid') & filters.incoming)
async def stickerid(bot, update):
    msg = update.reply_to_message
    if msg and msg.sticker:
        return await update.reply_text("Sticker ID:\n<code>" +
                                            html.escape(msg.sticker.file_id) + "</code>", parse_mode=enums.ParseMode.HTML)
    else:
        return await update.reply_text("<i>Please reply to a sticker to get its ID.</i>", parse_mode=enums.ParseMode.HTML)

@Client.on_message(filters.command('getsticker') & filters.incoming)
async def getsticker(bot, update):
    msg = update.reply_to_message
    chat_id = update.chat.id

    if msg and msg.sticker:
        # download() directly on the message's sticker
        file_path = await msg.download(file_name="sticker.png")
        await bot.send_document(chat_id, document=file_path)
        os.remove(file_path)
    else:
        await update.reply_text("<i>Please reply to a sticker for me to upload its PNG.</i>", parse_mode=enums.ParseMode.HTML)
@Client.on_message(filters.command("tts") & filters.text)
async def tts_handler(client: Client, message):
    # Extract text
    if not message.reply_to_message:
        if len(message.command) < 2:
            return await message.reply("Give me some text: <code>/tts enter per night ai</code>", quote=True, parse_mode=enums.ParseMode.HTML)
        text = message.text.split(" ", 1)[1]
    else:
        text = message.reply_to_message.text or message.reply_to_message.caption or ""
        if not text:
            return await message.reply("<i>Reply to a message with text or caption to convert to speech.</i>", quote=True, parse_mode=enums.ParseMode.HTML)
    lang = "ml"
    filename = f"{datetime.now().strftime('%d%m%y-%H%M%S%f')}.mp3"

    # Try generating Malayalam voice
    try:
        tts = gTTS(text, lang=lang)
        tts.save(filename)
        with open(filename, "rb") as f:
            if len(list(f)) == 1:
                raise ValueError("Malayalam TTS too short, fallback to English")
    except:
        # Fallback to English
        lang = "en"
        tts = gTTS(text, lang=lang)
        tts.save(filename)

    await client.send_chat_action(chat_id=message.chat.id, action=ChatAction.RECORD_AUDIO)

    await message.reply_voice(reply_to_message_id= message.reply_to_message.id if message.reply_to_message else message.id,voice=filename, quote=False)
    try:
        os.remove(filename)
    except Exception as e:
        await message.reply(f"Error removing file {filename}: {e}")

@Client.on_message(filters.command(['ud', 'urban']) & filters.text)
async def ud(bot, message):
    if len(message.command) < 2:
            return await message.reply("<b>Example:</b>\n<code>/ud incel</code>", quote=True)
    text = message.text.split(" ", 1)[1]
    results = requests.get(f'http://api.urbandictionary.com/v0/define?term={text}').json()
    try:
        reply_text = f'<b>📝 Word: {text}</b>\n\n<b>ℹ️ Definition</b>\n{results["list"][0]["definition"]}\n\n<b>📌 Example</b>\n<i>{results["list"][0]["example"]}</i>'
    except:
        reply_text = "<i>No results found.</i>"
    await message.reply_text(reply_text, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True, quote=True)


@Client.on_message(filters.command('weebify') & filters.text)
async def weebify(bot, update):
    if not update.reply_to_message:
        if len(update.command) < 2:
            return await update.reply("Give me some text: <code>/weebify helloworld</code>", quote=True, parse_mode=enums.ParseMode.HTML)
        text = update.text.split(" ", 1)[1]
    else:
        text = update.reply_to_message.text or update.reply_to_message.caption or ""
        if not text:
            return await update.reply("<i>Reply to a message with text or caption to convert to weebify.</i>", quote=True, parse_mode=enums.ParseMode.HTML)
    string = text.lower()
    normiefont = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u',
              'v', 'w', 'x', 'y', 'z']
    weebyfont = ['卂', '乃', '匚', '刀', '乇', '下', '厶', '卄', '工', '丁', '长', '乚', '从', '𠘨', '口', '尸', '㔿', '尺', '丂', '丅', '凵',
             'リ', '山', '乂', '丫', '乙']
    for normiecharacter in string:
        if normiecharacter in normiefont:
            weebycharacter = weebyfont[normiefont.index(normiecharacter)]
            string = string.replace(normiecharacter, weebycharacter)
    if update.reply_to_message:
        await update.reply_to_message.reply_text(string)
    else:
        await update.reply_text(string)

