import random
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from wallbot import wbot as app
from config import DB_URL


# MongoDB Connection
mongo_client = MongoClient(DB_URL)
db = mongo_client.pvp_game

# Collections
players_col = db.players
battles_col = db.battles
items_col = db.items

# Create indexes
players_col.create_index("user_id", unique=True)
battles_col.create_index("battle_id", unique=True)

# Game Configuration
INITIAL_HP = 100
INITIAL_ATTACK = 10
INITIAL_DEFENSE = 5
INITIAL_GOLD = 50

# Battle actions
ATTACK = "attack"
SPECIAL = "special"
HEAL = "heal"
FLEE = "flee"

class Player:
    def __init__(self, user_id, username, first_name):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.level = 1
        self.exp = 0
        self.hp = INITIAL_HP
        self.max_hp = INITIAL_HP
        self.attack = INITIAL_ATTACK
        self.defense = INITIAL_DEFENSE
        self.gold = INITIAL_GOLD
        self.inventory = []
        self.victories = 0
        self.defeats = 0
        self.last_battle = None
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "level": self.level,
            "exp": self.exp,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "attack": self.attack,
            "defense": self.defense,
            "gold": self.gold,
            "inventory": self.inventory,
            "victories": self.victories,
            "defeats": self.defeats,
            "last_battle": self.last_battle
        }
    
    @classmethod
    def from_dict(cls, data):
        player = cls(data["user_id"], data["username"], data["first_name"])
        player.level = data["level"]
        player.exp = data["exp"]
        player.hp = data["hp"]
        player.max_hp = data["max_hp"]
        player.attack = data["attack"]
        player.defense = data["defense"]
        player.gold = data["gold"]
        player.inventory = data["inventory"]
        player.victories = data["victories"]
        player.defeats = data["defeats"]
        player.last_battle = data["last_battle"]
        return player
    
    def level_up(self):
        exp_needed = self.level * 100
        if self.exp >= exp_needed:
            self.exp -= exp_needed
            self.level += 1
            self.max_hp += 20
            self.hp = self.max_hp
            self.attack += 5
            self.defense += 2
            return True
        return False
    
    def heal(self, amount):
        self.hp = min(self.hp + amount, self.max_hp)
        return self.hp

class Battle:
    def __init__(self, battle_id, player1, player2):
        self.battle_id = battle_id
        self.player1 = player1
        self.player2 = player2
        self.current_turn = player1.user_id
        self.turn_count = 0
        self.log = []
        self.status = "ongoing"  # ongoing, completed, fled
    
    def to_dict(self):
        return {
            "battle_id": self.battle_id,
            "player1": self.player1.to_dict(),
            "player2": self.player2.to_dict(),
            "current_turn": self.current_turn,
            "turn_count": self.turn_count,
            "log": self.log,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, data):
        battle = cls(
            data["battle_id"],
            Player.from_dict(data["player1"]),
            Player.from_dict(data["player2"])
        )
        battle.current_turn = data["current_turn"]
        battle.turn_count = data["turn_count"]
        battle.log = data["log"]
        battle.status = data["status"]
        return battle
    
    def switch_turn(self):
        self.current_turn = (
            self.player2.user_id 
            if self.current_turn == self.player1.user_id 
            else self.player1.user_id
        )
        self.turn_count += 1
    
    def get_current_player(self):
        return (
            self.player1 
            if self.current_turn == self.player1.user_id 
            else self.player2
        )
    
    def get_opponent(self):
        return (
            self.player2 
            if self.current_turn == self.player1.user_id 
            else self.player1
        )
    
    def add_log(self, message):
        self.log.append(f"Turn {self.turn_count}: {message}")
        if len(self.log) > 10:  # Keep only last 10 log entries
            self.log.pop(0)
    
    def perform_attack(self, attacker, defender, is_special=False):
        # Calculate damage
        base_damage = attacker.attack
        if is_special:
            base_damage *= 1.5  # Special attack does 50% more damage
            # Special attack has a 20% chance to miss
            if random.random() < 0.2:
                self.add_log(f"{attacker.first_name}'s special attack missed!")
                return 0
        
        damage = max(1, base_damage - defender.defense // 2)
        damage = min(damage, defender.hp)  # Don't deal more damage than target has HP
        
        # Critical hit chance (10%)
        is_critical = random.random() < 0.1
        if is_critical:
            damage *= 2
            self.add_log("Critical hit!")
        
        defender.hp -= damage
        
        attack_type = "special" if is_special else "attack"
        self.add_log(
            f"{attacker.first_name} used {attack_type} on {defender.first_name} "
            f"for {damage} damage! {'(Critical!)' if is_critical else ''}"
        )
        
        return damage
    
    def perform_heal(self, player):
        heal_amount = player.max_hp // 4  # Heal 25% of max HP
        player.heal(heal_amount)
        self.add_log(f"{player.first_name} healed for {heal_amount} HP!")
        return heal_amount

# Database operations
async def get_player(user_id: int, username: str = "", first_name: str = ""):
    player_data = players_col.find_one({"user_id": user_id})
    if player_data:
        return Player.from_dict(player_data)
    else:
        # Create new player
        new_player = Player(user_id, username, first_name)
        players_col.insert_one(new_player.to_dict())
        return new_player

async def update_player(player: Player):
    players_col.update_one(
        {"user_id": player.user_id},
        {"$set": player.to_dict()}
    )

async def create_battle(battle_id: str, player1: Player, player2: Player):
    battle = Battle(battle_id, player1, player2)
    battles_col.insert_one(battle.to_dict())
    return battle

async def get_battle(battle_id: str):
    battle_data = battles_col.find_one({"battle_id": battle_id})
    if battle_data:
        return Battle.from_dict(battle_data)
    return None

async def update_battle(battle: Battle):
    battles_col.update_one(
        {"battle_id": battle.battle_id},
        {"$set": battle.to_dict()}
    )

async def delete_battle(battle_id: str):
    battles_col.delete_one({"battle_id": battle_id})

# Battle actions
async def handle_battle_action(client, callback_query: CallbackQuery, action: str):
    user_id = callback_query.from_user.id
    battle_id = callback_query.data.split("_")[-1]
    
    battle = await get_battle(battle_id)
    if not battle or battle.status != "ongoing":
        await callback_query.answer("This battle has ended or doesn't exist!")
        return
    
    if battle.current_turn != user_id:
        await callback_query.answer("It's not your turn!")
        return
    
    current_player = battle.get_current_player()
    opponent = battle.get_opponent()
    
    if action == ATTACK:
        damage = battle.perform_attack(current_player, opponent)
        battle.switch_turn()
    elif action == SPECIAL:
        damage = battle.perform_attack(current_player, opponent, is_special=True)
        battle.switch_turn()
    elif action == HEAL:
        heal_amount = battle.perform_heal(current_player)
        battle.switch_turn()
    elif action == FLEE:
        battle.status = "fled"
        battle.add_log(f"{current_player.first_name} fled from battle!")
        # Penalty for fleeing
        current_player.gold = max(0, current_player.gold - 20)
        await update_player(current_player)
    
    # Check if battle is over
    if opponent.hp <= 0:
        battle.status = "completed"
        current_player.victories += 1
        current_player.exp += 50
        current_player.gold += 30
        
        opponent.defeats += 1
        opponent.exp += 10
        opponent.gold += 10
        
        # Level up if enough exp
        if current_player.level_up():
            battle.add_log(f"{current_player.first_name} leveled up to level {current_player.level}!")
        
        battle.add_log(f"{current_player.first_name} defeated {opponent.first_name}!")
        
        # Update players in database
        await update_player(current_player)
        await update_player(opponent)
    
    # Update battle in database
    await update_battle(battle)
    
    # Send updated battle message
    await send_battle_message(client, callback_query.message.chat.id, battle)
    
    await callback_query.answer()

async def send_battle_message(client, chat_id, battle):
    # Create battle status message
    p1 = battle.player1
    p2 = battle.player2
    
    # Health bars
    def create_health_bar(hp, max_hp, length=10):
        filled = int((hp / max_hp) * length)
        return "█" * filled + "░" * (length - filled)
    
    p1_bar = create_health_bar(p1.hp, p1.max_hp)
    p2_bar = create_health_bar(p2.hp, p2.max_hp)
    
    message = (
        f"⚔️ **Battle Between {p1.first_name} and {p2.first_name}** ⚔️\n\n"
        f"**{p1.first_name}** (Lv.{p1.level})\n"
        f"HP: {p1_bar} {p1.hp}/{p1.max_hp}\n\n"
        f"**{p2.first_name}** (Lv.{p2.level})\n"
        f"HP: {p2_bar} {p2.hp}/{p2.max_hp}\n\n"
    )
    
    if battle.status == "ongoing":
        current_player = battle.get_current_player()
        message += f"**{current_player.first_name}'s Turn**\n\n"
        message += "**Battle Log:**\n" + "\n".join(battle.log[-3:])
        
        # Create action buttons for current player
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗡 Attack", callback_data=f"battle_{ATTACK}_{battle.battle_id}"),
                InlineKeyboardButton("🔥 Special", callback_data=f"battle_{SPECIAL}_{battle.battle_id}")
            ],
            [
                InlineKeyboardButton("❤️ Heal", callback_data=f"battle_{HEAL}_{battle.battle_id}"),
                InlineKeyboardButton("🏃 Flee", callback_data=f"battle_{FLEE}_{battle.battle_id}")
            ]
        ])
    else:
        if battle.status == "fled":
            message += "**Battle ended: Someone fled!**\n"
        else:
            winner = p1 if p1.hp > 0 else p2
            message += f"**Battle ended: {winner.first_name} wins!**\n"
        
        message += "\n**Final Battle Log:**\n" + "\n".join(battle.log[-5:])
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 View Stats", callback_data=f"stats_{p1.user_id}_{p2.user_id}")]
        ])
    
    # Send or edit message
    try:
        await client.send_message(
            chat_id,
            message,
            reply_markup=keyboard
        )
    except:
        # If message exists, edit it
        pass

# Command handlers
@app.on_message(filters.command("jst"))
async def startssksksmmand(client, message: Message):
    user = message.from_user
    player = await get_player(user.id, user.username, user.first_name)
    
    welcome_text = (
        "🎮 **PvP Battle Game** 🎮\n\n"
        "Challenge other players to epic battles!\n\n"
        "**Available Commands:**\n"
        "/battle @username - Challenge a player\n"
        "/profile - View your profile\n"
        "/leaderboard - View top players\n"
        "/shop - View items for sale\n\n"
        "**Battle Actions:**\n"
        "• 🗡 Attack: Basic attack\n"
        "• 🔥 Special: Powerful attack (may miss)\n"
        "• ❤️ Heal: Restore some HP\n"
        "• 🏃 Flee: Escape battle (lose some gold)\n\n"
        "Start by challenging someone with /battle @username!"
    )
    
    await message.reply_text(welcome_text)

@app.on_message(filters.command("profile"))
async def profile_command(client, message: Message):
    user = message.from_user
    player = await get_player(user.id, user.username, user.first_name)
    
    profile_text = (
        f"👤 **{player.first_name}'s Profile**\n\n"
        f"**Level:** {player.level}\n"
        f"**EXP:** {player.exp}/{player.level * 100}\n"
        f"**HP:** {player.hp}/{player.max_hp}\n"
        f"**Attack:** {player.attack}\n"
        f"**Defense:** {player.defense}\n"
        f"**Gold:** {player.gold} 🪙\n\n"
        f"**Battles:** {player.victories} wins, {player.defeats} losses\n"
        f"**Win Rate:** {player.victories/(player.victories+player.defeats)*100:.1f}%"
        if player.victories + player.defeats > 0 else "No battles yet"
    )
    
    await message.reply_text(profile_text)

@app.on_message(filters.command("battle"))
async def battle_command(client, message: Message):
    if not message.reply_to_message and len(message.command) < 2:
        await message.reply_text("Please mention a user to battle: /battle @username")
        return
    
    # Get challenger
    challenger = await get_player(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    # Get opponent
    if message.reply_to_message:
        opponent_user = message.reply_to_message.from_user
    else:
        try:
            opponent_mention = message.command[1]
            if opponent_mention.startswith("@"):
                # This is a simplified approach - in reality you'd need to resolve the username
                await message.reply_text("Please reply to the user's message or use their ID")
                return
            else:
                opponent_id = int(opponent_mention)
                # In a real implementation, you'd fetch the user by ID
                await message.reply_text("Please reply to the user's message for now")
                return
        except (IndexError, ValueError):
            await message.reply_text("Invalid user specified")
            return
    
    opponent = await get_player(
        opponent_user.id,
        opponent_user.username,
        opponent_user.first_name
    )
    
    # Check if trying to battle self
    if challenger.user_id == opponent.user_id:
        await message.reply_text("You can't battle yourself!")
        return
    
    # Check if opponent has enough HP
    if opponent.hp <= 0:
        await message.reply_text(f"{opponent.first_name} is too weak to battle! They need to heal first.")
        return
    
    # Create battle
    battle_id = f"{challenger.user_id}_{opponent.user_id}_{datetime.now().timestamp()}"
    battle = await create_battle(battle_id, challenger, opponent)
    
    # Send battle message
    await send_battle_message(client, message.chat.id, battle)
    
    # Notify opponent if they're in the chat
    try:
        await client.send_message(
            message.chat.id,
            f"⚔️ {opponent.first_name}, you've been challenged by {challenger.first_name}!",
            reply_to_message_id=message.id
        )
    except:
        pass

@app.on_message(filters.command("leaderboard"))
async def leaderboard_command(client, message: Message):
    # Get top 10 players by level or victories
    top_players = players_col.find().sort("victories", -1).limit(10)
    
    leaderboard_text = "🏆 **Top Players** 🏆\n\n"
    
    for i, player_data in enumerate(top_players):
        player = Player.from_dict(player_data)
        leaderboard_text += f"{i+1}. {player.first_name} - Lv.{player.level} - {player.victories} wins\n"
    
    await message.reply_text(leaderboard_text)

@app.on_message(filters.command("heal"))
async def heal_command(client, message: Message):
    user = message.from_user
    player = await get_player(user.id, user.username, user.first_name)
    
    # Heal at the cost of gold
    heal_cost = 10
    if player.gold < heal_cost:
        await message.reply_text(f"You need {heal_cost} gold to heal! You have {player.gold} gold.")
        return
    
    if player.hp >= player.max_hp:
        await message.reply_text("You're already at full health!")
        return
    
    player.gold -= heal_cost
    old_hp = player.hp
    player.heal(player.max_hp)  # Full heal
    
    await update_player(player)
    
    await message.reply_text(
        f"❤️ You've been healed for {player.hp - old_hp} HP!\n"
        f"Now at {player.hp}/{player.max_hp} HP\n"
        f"Remaining gold: {player.gold} 🪙"
    )

# Callback query handlers
@app.on_callback_query(filters.regex("^battle_"))
async def battle_callback_handler(client, callback_query: CallbackQuery):
    action = callback_query.data.split("_")[1]
    await handle_battle_action(client, callback_query, action)

@app.on_callback_query(filters.regex("^stats_"))
async def stats_callback_handler(client, callback_query: CallbackQuery):
    user_id1, user_id2 = map(int, callback_query.data.split("_")[1:3])
    
    player1 = await get_player(user_id1)
    player2 = await get_player(user_id2)
    
    stats_text = (
        f"📊 **Battle Statistics**\n\n"
        f"**{player1.first_name}**\n"
        f"Level: {player1.level}\n"
        f"Wins: {player1.victories}\n"
        f"Losses: {player1.defeats}\n\n"
        f"**{player2.first_name}**\n"
        f"Level: {player2.level}\n"
        f"Wins: {player2.victories}\n"
        f"Losses: {player2.defeats}\n\n"
    )
    
    await callback_query.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch_{user_id1}_{user_id2}")]
        ])
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^rematch_"))
async def rematch_callback_handler(client, callback_query: CallbackQuery):
    user_id1, user_id2 = map(int, callback_query.data.split("_")[1:3])
    
    player1 = await get_player(user_id1)
    player2 = await get_player(user_id2)
    
    # Check if players have enough HP
    if player1.hp <= 0:
        await callback_query.answer(f"{player1.first_name} is too weak to battle!", show_alert=True)
        return
    
    if player2.hp <= 0:
        await callback_query.answer(f"{player2.first_name} is too weak to battle!", show_alert=True)
        return
    
    # Create new battle
    battle_id = f"{player1.user_id}_{player2.user_id}_{datetime.now().timestamp()}"
    battle = await create_battle(battle_id, player1, player2)
    
    # Send battle message
    await send_battle_message(client, callback_query.message.chat.id, battle)
    
    await callback_query.answer()

