import asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from main import wbot as word

from main import WORD_SET
from wallbot.database.db import update_stats, get_stats

from datetime import datetime
import random
from datetime import timedelta

active_games = {}
pending_games = {}

class Game:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = []
        self.starter = None
        self.start_time = None
        self.current_word = None
        self.used_words = set()
        self.turn_index = 0
        self.time_left = 45
        self.word_length = 3
        self.word_count = 0
        self.consecutive_count = 0

    async def start_countdown(self, delay=60):
        delays = [60, 30, 15, 10]
        for delay in delays:
            if self.chat_id in active_games:
                return
            if delay == 60:
                await word.send_message(self.chat_id, "The classic game is starting in 1 minute - join now!\n\nRules:\n- 45s per word\n- Start with 3-letter words\n- Every 4 words reduce time by 10s\n- Every 2 words increase length by 1")
            else:
                await word.send_message(self.chat_id, f"Starting game in {delay} seconds...")
            await asyncio.sleep(delay if delay == 60 else delays[delays.index(delay) - delays[delays.index(delay)+1]] if delays.index(delay)+1 < len(delays) else delay)
        if self.chat_id in active_games:
            return
        if len(self.players) >= 2:
            await self.start_game()
        else:
            await word.send_message(self.chat_id, "Not enough players to start the game!")
            del pending_games[self.chat_id]

    async def start_game(self):
        self.start_time = datetime.now()
        active_games[self.chat_id] = self
        del pending_games[self.chat_id]
        self.current_word = random.choice('abcdefghijklmnopqrstuvwxyz').upper()
        turn_order = "\n".join([f"• {p['mention']}" for p in self.players])
        await word.send_message(self.chat_id, f"Game Started!\n\nFirst letter: **{self.current_word}**\nTurn order:\n{turn_order}")
        await self.next_turn()

    async def next_turn(self):
        
        if self.chat_id not in active_games:
            return
        if not self.players:
            await word.send_message(self.chat_id, "No players left! Ending game.")
            del active_games[self.chat_id]
            return
        if self.time_left <= 0:
            return await self.handle_timeout()
        player = self.players[self.turn_index]
        cache_total_players = {}
        for p in self.players:
            cache_total_players[p['id']] = p['mention']
        await word.send_message(self.chat_id, 
            f"Turn: {player['mention']} (Next: {self.players[(self.turn_index+1)%len(self.players)]['mention']})\n"
            f"Your word must start with **{self.current_word[-1].upper()}**\n"
            f"Minimum length: {self.word_length} letters\n"
            f"Time left: {self.time_left}s\n"
            f"Players: {len(self.players)}/{len(cache_total_players)}\n"
            f"Total words: {self.word_count}")
        try:
            answer = await word.listen(filters=filters.user(player['id']) & filters.chat(self.chat_id) & filters.text, timeout=self.time_left)
            await self.validate_word(answer)
        except:
            await self.handle_timeout()

    async def validate_word(self, msg: Message):
        wordd = msg.text.lower().strip()
        if wordd and not wordd.startswith(self.current_word[-1].lower()):
            await msg.reply(f"{wordd} does not start with **{self.current_word[-1].upper()}**!")
            return await self.next_turn()
        if len(wordd) < self.word_length:
            await msg.reply(f"{wordd} has less than {self.word_length} letters.")
            return await self.next_turn()
        if wordd not in WORD_SET:
            await msg.reply(f"{wordd} is not in my list of words!")
            return await self.next_turn()
        if wordd in self.used_words:
            await msg.reply(f"{wordd} has been used!")
            return await self.next_turn()
        if len(wordd) < self.word_length or wordd[0] != self.current_word[-1].lower() or wordd in self.used_words or wordd not in WORD_SET:
            return await self.next_turn()
        self.used_words.add(wordd)
        self.current_word = wordd
        self.word_count += 1
        self.consecutive_count += 1
        if self.consecutive_count % 4 == 0:
            self.time_left = max(15, self.time_left - 10)
        if self.consecutive_count % 2 == 0:
            self.word_length += 1
        await update_stats(msg.from_user.id, "total_words", 1)
        await update_stats(msg.from_user.id, "total_letters", len(wordd))
        self.turn_index = (self.turn_index + 1) % len(self.players)
        await word.send_message(self.chat_id, f"__{wordd.capitalize()}__ accepted!")
        await self.next_turn()

    async def handle_timeout(self):
        player = self.players.pop(self.turn_index)
        await word.send_message(self.chat_id, f"{player['mention']} ran out of time! Eliminated!")
        if len(self.players) == 1:
            winner = self.players[0]
            duration = datetime.now() - self.start_time
            formatted_duration = str(timedelta(seconds=int(duration.total_seconds())))
            longest = max(self.used_words, key=len) if self.used_words else "N/A"
            await word.send_message(self.chat_id, 
                f"🏆 {winner['mention']} won!\n"
                f"Total words: {self.word_count}\n"
                f"Longest word: {longest} ({len(longest)} letters)\n"
                f"Duration: {formatted_duration}\n")
            await update_stats(winner['id'], "games_won", 1)
            for player in self.players:
                await update_stats(player['id'], "games_played", 1)
            if longest:
                stats = await get_stats(winner['id'])
                prev_longest = stats.get('longest_word', '')
                if len(longest) > len(prev_longest):
                    await update_stats(winner['id'], "longest_word", longest)
            del active_games[self.chat_id]
        else:
            self.turn_index %= len(self.players)
            await self.next_turn()

@word.on_message(filters.command("startclassic") & filters.group)
async def start_classic(client, message: Message):
    chat_id = message.chat.id
    if chat_id in pending_games:
        return await message.reply("A game is already pending!")
    
    game = Game(chat_id)
    pending_games[chat_id] = game
    game.starter = message.from_user.id
    await message.reply("Classic game started! Type /joinx to participate!")
    asyncio.create_task(game.start_countdown())
    gamee = pending_games[chat_id]
    gamee.players.append({
        'id': message.from_user.id,
        'mention': message.from_user.mention
    })
    await message.reply(f"{message.from_user.mention} joined the game!")

@word.on_message(filters.command("joinx") & filters.group)
async def join_gaxme(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in pending_games:
        return await message.reply("No pending game to join!")
    
    game = pending_games[chat_id]
    if any(p['id'] == message.from_user.id for p in game.players):
        return await message.reply("You're already in the game!")
    
    game.players.append({
        'id': message.from_user.id,
        'mention': message.from_user.mention
    })
    await message.reply(f"{message.from_user.mention} joined the game!")

@word.on_message(filters.command("leavex") & filters.group)
async def fleex_game(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in pending_games:
        return await message.reply("No pending game to leave!")
    
    game = pending_games[chat_id]
    game.players = [p for p in game.players if p['id'] != message.from_user.id]
    await message.reply("You left the game!")

@word.on_message(filters.command("extendx") & filters.group)
async def extend_xgame(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in pending_games:
        return await message.reply("No active game to extend!")
    
    game = pending_games[chat_id]
    await game.start_countdown(30)
    await message.reply(f"Game start extended by 30 seconds!\n\nNew start time: {game.start_time + timedelta(seconds=30)}")

@word.on_message(filters.command("statsx"))
async def show_stdats(client, message: Message):
    stats = await get_stats(message.from_user.id)
    
    games_played = stats.get('games_played', 0)
    games_won = stats.get('games_won', 0)

    await message.reply(
        f"📊 Statistics for {message.from_user.mention}:\n"
        f"• {games_played} games played\n"
        f"• {games_won} won\n"
        f"• {stats.get('total_words', 0)} total words\n"
        f"• {stats.get('total_letters', 0)} total letters\n"
        f"• Longest word: {stats.get('longest_word', 'None')}"
    )

@word.on_message(filters.command("forcestartx") & filters.group)
async def force_start(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in pending_games:
        return await message.reply("No pending game to force start!")
    
    game = pending_games[chat_id]
    if message.from_user.id != game.starter:
        return await message.reply("Only the game starter can force start the game!")
    
    await game.start_game()
