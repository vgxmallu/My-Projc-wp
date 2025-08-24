from pyrogram import filters
from wallbot import wbot as bot
from pyrogram.types import Message
import os
import asyncio 
from pyrogram import enums
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

chatQueue = []

stopProcess = False

@bot.on_message(filters.command(["tagall","mentionall","all","mention"]))
async def everyone(_, message):
  global stopProcess
  try: 
    try:
      sender = await bot.get_chat_member(message.chat.id, message.from_user.id)
      has_permissions = sender.privileges
    except:
      has_permissions = message.sender_chat  
    if has_permissions:
      if len(chatQueue) > 5:
        await message.reply("-› I'm already working on my maximum number of 5 chats at the moment. Please try again shortly.")
      else:  
        if message.chat.id in chatQueue:
          await message.reply("-› There's already an ongoing process in this chat. Please /stop to start a new one.")
        else:  
          chatQueue.append(message.chat.id)
          if len(message.command) > 1:
            inputText = " ".join(message.command[1:])
          elif len(message.command) == 1:
            inputText = ""    
          membersList = []
          async for member in bot.get_chat_members(message.chat.id):
            if member.user.is_bot == True:
              pass
            elif member.user.is_deleted == True:
              pass
            else:
              membersList.append(member.user)
          i = 0
          lenMembersList = len(membersList)
          if stopProcess: stopProcess = False
          while len(membersList) > 0 and not stopProcess :
            j = 0
            text1 = f"{inputText}\n\n"
            try:    
              while j < 10:
                user = membersList.pop(0)
                if user.username == None:
                  text1 += f"{user.mention} "
                  j+=1
                else:
                  text1 += f"@{user.username} "
                  j+=1
              try:     
                await bot.send_message(message.chat.id, text1)
              except Exception:
                pass  
              await asyncio.sleep(1) 
              i+=10
            except IndexError:
              try:
                await bot.send_message(message.chat.id, text1)  
              except Exception:
                pass  
              i = i+j
          if i == lenMembersList:    
            await message.reply(f"-› Successfully mentioned **total number of {i} members**.\n-› Bots and deleted accounts were rejected.") 
          else:
            await message.reply(f"-› Successfully mentioned **{i} members.**\n-› Bots and deleted accounts were rejected.")    
          chatQueue.remove(message.chat.id)
    else:
      await message.reply("-› Sorry, **only admins** can execute this command.")  
  except FloodWait as e:
    await asyncio.sleep(e.value)                    
        
@bot.on_message(filters.command(["stop","cancel"]))
async def stop(_, message):
  global stopProcess
  try:
    try:
      sender = await bot.get_chat_member(message.chat.id, message.from_user.id)
      has_permissions = sender.privileges
    except:
      has_permissions = message.sender_chat  
    if has_permissions:
      if not message.chat.id in chatQueue:
        await message.reply("-› There is no ongoing process to stop.")
      else:
        stopProcess = True
        await message.reply("-› Stopped.")
    else:
      await message.reply("-› Sorry, **only admins** can execute this command.")
  except FloodWait as e:
    await asyncio.sleep(e.value)
