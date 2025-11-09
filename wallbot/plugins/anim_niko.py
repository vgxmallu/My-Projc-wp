import logging, os, random
from pyrogram import filters, Client, __version__ as pyro
from pyrogram.types import *

import requests 
from main import wbot as bot

PM_START_TEXT = """
**Welcome** {}~kun ฅ(≈>ܫ<≈)
`I'm A Neko Themed Telegram Bot Using Nekos.best! `
**Make Your Groups Active By Adding Me There! ××**
"""


HELP_TEXT = """
**Anime Themed SFW:**
• Kiss : /kiss To Kiss A Person
• Highfive : /highfive To Highfive A Person
• Happy : /happy To Makes A Person Happy
• Laugh : /laugh To Makes A Person Laugh
• Bite : /bite To Bite A Person
• Poke : /poke To Poke A Person
• Tickle : /tickle To Tickle A Person
• Wave : /wave To Wave A Person
• Thumbsup : /thumbsup To Thumbsup A Person
• Stare : /stare To Makes A Person Stare
• Cuddle : /cuddle To Cuddle A Person
• Smile : /smile To Makes A Person Smile
• Baka : /baka To Say A Person Baka
• Blush : /blush To Makes A Person Blush

• **Message as to Lang below click the more button know more commandslist!**
"""


ABOUT_TEXT = """
**Hello Dear Users!**
`I'm A Neko Themed Telegram Bot Using Nekos.best! `

My Pyroversion: {}
My updates : [Nandhabots](https://t.me/nandhabots)
My support : [NandhaSupport](https://t.me/nandhasupport)

[Source](https://github.com/ctzfamily/neko-best-bot) ✨

My All Credits fosto:
[Nandha](https://t.me/nandhaxd) |  [AASF](https://t.me/pro_x_d)
"""


MORE_HELP_TEXT = """
**Anime themed SFW:**
• Think : /think To Makes A Person Think
• Pout : /pout To Makes A Person Pout
• Facepalm : /facepalm To Makes A Person Facepalm
• Wink : /wink To Makes A Person Wink
• Smug : /smug To Makes A Person Smug
• Cry : /cry To Makes A Person Cry
• Dance : /dance To Makes A Person Dance
• Feed : /feed To Feed A Person
• Shrug : /shrug To Shrug A Person
• Bored : /bored To Makes A Person Bored
• Pat : /pat To Pat A Person
• Hug : /hug To Hug A Person
• Slap : /slap To Slap A Person
• Cute : /cute To Say Me Cute
• Waifu : /waifu To Send Random Waifu Image
• Kitsune : /kitsune To Send Random Kitsune Image
• Sleep : /sleep To Say I Am Going To Sleep
• Neko : /neko To Get Random Neko quotes
"""

OWO = (
    "*Neko pats {} on the head.",
    "*gently rubs {}'s head*.",
    "*Neko mofumofus {}'s head*",
    "*Neko messes up {}'s head*",
    "*Neko intensly rubs {}'s head*",
    "*{}'s waifu pats their head*",
    "*{}'s got free headpats*",
    "No pats for {}!",
)

neko_text = (
 "(*)^(*) *lazy arrival* zzzZZ(Z){}-kun I'm hungry...",
 "OwO why are calling me *wags tail in excitement* {} Do you have have cookies?",
 "^~^ *peeks by wall* Oh! {} Meowwww",
 "Ara Ara! {} Do you wanna play? *raises cat ears* ^attentive^",
 "($^$) *money face* {} are you rich UwU?",
 "Hello UwU {} I'm here to play, Meow"
)


@bot.on_message(filters.command("nkiss"))
async def jkkiss(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/kiss"
       r = requests.get(url)
       e = r.json()
       kissme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(kissme, caption="*{} kisses {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/kiss"
      r = requests.get(url)
      e = r.json()
      kissme = e["results"][0]["url"]
      await message.reply_video(kissme, caption="*Kisses u with all my love*~")
      return

@bot.on_message(filters.command("highfive"))
async def highfive(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/highfive"
       r = requests.get(url)
       e = r.json()
       highfiveme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(highfiveme, caption="*{} highfives {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/highfive"
      r = requests.get(url)
      e = r.json()
      highfiveme = e["results"][0]["url"]
      await message.reply_video(highfiveme, caption="*Highfives U With All My Friendship*~")
      return

@bot.on_message(filters.command("nhappy"))
async def hhappy(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/happy"
       r = requests.get(url)
       e = r.json()
       happyme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(happyme, caption="*{} Is So Happy Today Did You Know {} ?*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/happy"
      r = requests.get(url)
      e = r.json()
      happyme = e["results"][0]["url"]
      await message.reply_video(happyme, caption="*U So Happy Today But Why*~")
      return

@bot.on_message(filters.command("nlaugh"))
async def ljaugh(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/laugh"
       r = requests.get(url)
       e = r.json()
       laughme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(laughme, caption="*{} Is Laughed By {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/laugh"
      r = requests.get(url)
      e = r.json()
      laughme = e["results"][0]["url"]
      await message.reply_video(laughme, caption="*I Can't Control Laughing*~")
      return

@bot.on_message(filters.command("nbite"))
async def ubite(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/bite"
       r = requests.get(url)
       e = r.json()
       biteme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(biteme, caption="*{} Bites {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/bite"
      r = requests.get(url)
      e = r.json()
      biteme = e["results"][0]["url"]
      await message.reply_video(biteme, caption="*Bites u with all my strength*~")
      return

@bot.on_message(filters.command("npooke"))
async def pohke(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/poke"
       r = requests.get(url)
       e = r.json()
       pokeme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(pokeme, caption="*{} pokes {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/poke"
      r = requests.get(url)
      e = r.json()
      pokeme = e["results"][0]["url"]
      await message.reply_video(pokeme, caption="*Poking You Continuously*~")
      return

@bot.on_message(filters.command("tickle"))
async def tickle(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/tickle"
       r = requests.get(url)
       e = r.json()
       tickleme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(tickleme, caption="*{} tickles {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/tickle"
      r = requests.get(url)
      e = r.json()
      tickleme = e["results"][0]["url"]
      await message.reply_video(tickleme, caption="*Tickling You Continuously Don't Laugh*~")
      return

@bot.on_message(filters.command("nwave"))
async def wiave(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/wave"
       r = requests.get(url)
       e = r.json()
       waveme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(waveme, caption="*{} waves {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/wave"
      r = requests.get(url)
      e = r.json()
      waveme = e["results"][0]["url"]
      await message.reply_video(waveme, caption="*My Hand Waving To You*~")
      return

@bot.on_message(filters.command("thumbsup"))
async def thumbsup(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/thumbsup"
       r = requests.get(url)
       e = r.json()
       thumbsupme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(thumbsupme, caption="*{} thumbsups with {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/thumbsup"
      r = requests.get(url)
      e = r.json()
      thumbsupme = e["results"][0]["url"]
      await message.reply_video(thumbsupme, caption="*Hey Come Let's Thumbsup*~")
      return

@bot.on_message(filters.command("stare"))
async def stare(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/stare"
       r = requests.get(url)
       e = r.json()
       stareme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(stareme, caption="*{} stares {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/stare"
      r = requests.get(url)
      e = r.json()
      stareme = e["results"][0]["url"]
      await message.reply_video(stareme, caption="*What You Said Say It Again*~")
      return

@bot.on_message(filters.command("cuddle"))
async def cuddle(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/cuddle"
       r = requests.get(url)
       e = r.json()
       cuddleme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(cuddleme, caption="*{} cuddles {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/cuddle"
      r = requests.get(url)
      e = r.json()
      cuddleme = e["results"][0]["url"]
      await message.reply_video(cuddleme, caption="*Cuddle u with all my love*~")
      return

@bot.on_message(filters.command("nsmile"))
async def snmile(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/smile"
       r = requests.get(url)
       e = r.json()
       smileme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(smileme, caption="*{} smiles by seeing {}'s face*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/smile"
      r = requests.get(url)
      e = r.json()
      smileme = e["results"][0]["url"]
      await message.reply_video(smileme, caption="*Is Smiles Looking Beautiful ?*~")
      return

@bot.on_message(filters.command("baka"))
async def baka(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/baka"
       r = requests.get(url)
       e = r.json()
       bakame = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(bakame, caption="*{} said {} is baka*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/baka"
      r = requests.get(url)
      e = r.json()
      bakame = e["results"][0]["url"]
      await message.reply_video(bakame, caption="*You A Stupid Baka!*~")
      return

@bot.on_message(filters.command("blush"))
async def blush(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/blush"
       r = requests.get(url)
       e = r.json()
       blushme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(blushme, caption="*{} blushes by seeing {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/blush"
      r = requests.get(url)
      e = r.json()
      blushme = e["results"][0]["url"]
      name1 = message.from_user.first_name
      await message.reply_video(blushme, caption="*Oh {}~kun I Luv You*~".format(name1))
      return

@bot.on_message(filters.command("think"))
async def thmkink(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/think"
       r = requests.get(url)
       e = r.json()
       thinkme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(thinkme, caption="*{} thoughts about {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/think"
      r = requests.get(url)
      e = r.json()
      thinkme = e["results"][0]["url"]
      name = message.from_user.first_name
      await message.reply_video(thinkme, caption="*{}~kun Do You Love Me?*~".format(name))
      return

@bot.on_message(filters.command("npout"))
async def ponut(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/pout"
       r = requests.get(url)
       e = r.json()
       poutme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(poutme, caption="*{} pouts {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/pout"
      r = requests.get(url)
      e = r.json()
      name = message.from_user.first_name
      poutme = e["results"][0]["url"]
      await message.reply_video(poutme, caption="*Oi {}~kun*~".format(name))
      return

@bot.on_message(filters.command("facepalm"))
async def facehpalm(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/facepalm"
       r = requests.get(url)
       e = r.json()
       facepalmme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(facepalmme, caption="*{} Made {} To Facepalm*~".format(name2, name1))
       return
    else:
      url = "https://nekos.best/api/v2/facepalm"
      r = requests.get(url)
      e = r.json()
      name = message.from_user.first_name
      facepalmme = e["results"][0]["url"]
      await message.reply_video(facepalmme, caption="*Oh Shit {}~kun*~".format(name))
      return

@bot.on_message(filters.command("nwink"))
async def winnk(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/wink"
       r = requests.get(url)
       e = r.json()
       winkme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(winkme, caption="*{} winks {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/wink"
      r = requests.get(url)
      e = r.json()
      winkme = e["results"][0]["url"]
      await message.reply_video(winkme, caption="*Winks u with all my love*~")
      return

@bot.on_message(filters.command("nsmug"))
async def smnug(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/smug"
       r = requests.get(url)
       e = r.json()
       smugme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(smugme, caption="*{} sumgs {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/smug"
      r = requests.get(url)
      e = r.json()
      smugme = e["results"][0]["url"]
      await message.reply_video(smugme, caption="*Hehehehehehehehe*~")
      return

@bot.on_message(filters.command("ncry"))
async def cnry(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/cry"
       r = requests.get(url)
       e = r.json()
       cryme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(cryme, caption="*{} is cried did you know {}?*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/cry"
      r = requests.get(url)
      e = r.json()
      cryme = e["results"][0]["url"]
      await message.reply_video(cryme, caption="*I Can't Stop Crying*~")
      return

@bot.on_message(filters.command("ndance"))
async def dannce(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/dance"
       r = requests.get(url)
       e = r.json()
       danceme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(danceme, caption="*{} danced with {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/dance"
      r = requests.get(url)
      e = r.json()
      name = message.from_user.first_name
      danceme = e["results"][0]["url"]
      await message.reply_video(danceme, caption="*{}~kun. Can You Dance With Me*~".format(name))
      return

@bot.on_message(filters.command("nfeed"))
async def femed(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/feed"
       r = requests.get(url)
       e = r.json()
       feedme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(feedme, caption="*{} feeds {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/feed"
      r = requests.get(url)
      e = r.json()
      feedme = e["results"][0]["url"]
      name = message.from_user.first_name
      await message.reply_video(feedme, caption="*Open You Mouth {}~kun*~".format(name))
      return

@bot.on_message(filters.command("nshrug"))
async def nshrug(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/shrug"
       r = requests.get(url)
       e = r.json()
       shrugme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(shrugme, caption="*{} shrugs to {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/shrug"
      r = requests.get(url)
      e = r.json()
      name = message.from_user.first_name
      shrugme = e["results"][0]["url"]
      await message.reply_video(shrugme, caption="*I Don't Know About It {}~kun*~".format(name))
      return

@bot.on_message(filters.command("nbored"))
async def borned(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/bored"
       r = requests.get(url)
       e = r.json()
       boredme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(boredme, caption="*{} bored to see {}*~".format(name1, name2))
       return
    else:
      url = "https://nekos.best/api/v2/bored"
      r = requests.get(url)
      e = r.json()
      name = message.from_user.first_name
      boredme = e["results"][0]["url"]
      await message.reply_video(boredme, caption="*Today Was So Boring {}~kun Any Idea?*~".format(name))
      return


@bot.on_message(filters.command("npat"))
async def npat(_, message):
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/pat"
       r = requests.get(url)
       e = r.json()
       patme = e["results"][0]["url"]
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(patme, caption="*{} pats {}*~".format(name1, name2))
    else:    
      name = (
          message.reply_to_message.from_user.first_name
          if message.reply_to_message
          else message.from_user.first_name
      )
      url = "https://nekos.best/api/v2/pat"
      r = requests.get(url)
      e = r.json()
      patme = e["results"][0]["url"]
      await message.reply_video(patme, caption=random.choice(OWO).format(name))

@bot.on_message(filters.command("nhug"))
async def hnug(_, message):
    
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/hug"
       r = requests.get(url)
       e = r.json()
       hugme = e["results"][0]["url"]
       
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(hugme, caption="*{} hugs {}*".format(name1, name2))
    else:
       url = "https://nekos.best/api/v2/hug"
       r = requests.get(url)
       e = r.json()
       hugme = e["results"][0]["url"]
       
       await message.reply_video(hugme, caption="*Hugs u with all my love*~")

@bot.on_message(filters.command("nslap"))      
async def slnap(_, message):
    
    if message.reply_to_message:
       url = "https://nekos.best/api/v2/slap"
       r = requests.get(url)
       e = r.json()
       slapme = e["results"][0]["url"]
       
       name1 = message.from_user.first_name
       name2 = message.reply_to_message.from_user.first_name
       await message.reply_to_message.reply_video(slapme, caption="*{} slaps {}*".format(name1, name2))
    else:
       url = "https://nekos.best/api/v2/slap"
       r = requests.get(url)
       e = r.json()
       slapme = e["results"][0]["url"]
       
       await message.reply_video(slapme, caption="Here... Take this from me.")

@bot.on_message(filters.command("ncute"))
async def cutne(_, message):
    name = message.from_user.first_name         
    url = f"https://nekos.best/api/v2/neko"
    r = requests.get(url)
    e = r.json()
    cuteme = e["results"][0]["url"]
    await message.reply_photo(
        cuteme, caption="Thank UwU {}-Kun  *smiles and hides ^~^*".format(name)
    )

@bot.on_message(filters.command("waifu"))
async def waifu(_, message):
    name = message.from_user.first_name         
    url = f"https://nekos.best/api/v2/waifu"
    r = requests.get(url)
    e = r.json()
    waifume = e["results"][0]["url"]
    await message.reply_photo(
        waifume, caption="Here I Am {}-Kun's *Waifu*".format(name)
    )

@bot.on_message(filters.command("kitsune"))
async def kitsune(_, message):
    name = message.from_user.first_name         
    url = f"https://nekos.best/api/v2/kitsune"
    r = requests.get(url)
    e = r.json()
    kitsuneme = e["results"][0]["url"]
    await message.reply_photo(
        kitsuneme, caption="Did You Called Me {}-Kun's *?*".format(name)
    )

@bot.on_message(filters.command("nsleep"))
async def slenep(_, message):
    sleep_type = random.choice(("Text", "Gif", "Video"))
    if sleep_type == "Gif":
        try:
            url = "https://nekos.best/api/v2/sleep"
            r = requests.get(url)
            e = r.json()
            sleepme = e["results"][0]["url"]
            await message.reply_video(sleepme)
        except BadRequest:
            sleep_type = "Text"

    if sleep_type == "Video":
        try:
            bed = "https://telegra.ph/file/f0fb71c72e059de34b565.mp4"
            await message.reply_video(bed)
        except BadRequest:
            sleep_type = "Text"

    if sleep_type == "Text":
        z = ". . . (∪｡∪)｡｡｡zzzZZ"
        await message.reply_text(z)

@bot.on_message(filters.command("neko"))
async def neko(_, message):
    name = message.from_user.first_name
    ke = random.choice(neko_text)
    await message.reply_text(
        ke.format(name)
    )
