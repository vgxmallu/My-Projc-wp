import os
import random
import asyncio
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, ReplyKeyboardMarkup, ForceReply
)
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import aiohttp
from config import DB_URL
from wallbot import wbot as app

# Database Connection

mongo_client = MongoClient(DB_URL)
db = mongo_client.advanced_pvp_game

# Collections
players_col = db.players
battles_col = db.battles
guilds_col = db.guilds
items_col = db.items
skills_col = db.skills
quests_col = db.quests
events_col = db.events
market_col = db.market
cooldowns_col = db.cooldowns  # New collection for cooldowns

# Create indexes
players_col.create_index("user_id", unique=True)
players_col.create_index("guild_id")
battles_col.create_index("battle_id", unique=True)
battles_col.create_index([("participants.user_id", 1)])
guilds_col.create_index("guild_id", unique=True)
guilds_col.create_index("name", unique=True)
cooldowns_col.create_index([("user_id", 1), ("type", 1)], unique=True)
cooldowns_col.create_index("expire_at", expireAfterSeconds=0)

# Game Configuration
INITIAL_STATS = {
    "hp": 100,
    "max_hp": 100,
    "mp": 50,
    "max_mp": 50,
    "attack": 10,
    "defense": 5,
    "magic": 5,
    "speed": 5,
    "stamina": 100,
    "gold": 100,
    "gems": 5
}

# Enums for game elements
class Element(Enum):
    FIRE = "fire"
    WATER = "water"
    EARTH = "earth"
    AIR = "air"
    LIGHT = "light"
    DARK = "dark"

class Rarity(Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"

class BattleType(Enum):
    DUEL = "duel"
    TEAM = "team"
    BATTLE_ROYALE = "battle_royale"
    RAID = "raid"
    TOURNAMENT = "tournament"

# Advanced Player Class
class AdvancedPlayer:
    def __init__(self, user_id, username, first_name):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.level = 1
        self.exp = 0
        self.stats = INITIAL_STATS.copy()
        self.equipment = {
            "weapon": None,
            "armor": None,
            "accessory": None
        }
        self.inventory = []
        self.skills = []
        self.quests = []
        self.guild_id = None
        self.guild_role = None
        self.title = "Novice"
        self.achievements = []
        self.pvp_stats = {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "kills": 0,
            "deaths": 0,
            "damage_dealt": 0,
            "damage_taken": 0
        }
        self.element = random.choice(list(Element)).value
        self.last_active = datetime.now()
        self.created_at = datetime.now()
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "level": self.level,
            "exp": self.exp,
            "stats": self.stats,
            "equipment": self.equipment,
            "inventory": self.inventory,
            "skills": self.skills,
            "quests": self.quests,
            "guild_id": self.guild_id,
            "guild_role": self.guild_role,
            "title": self.title,
            "achievements": self.achievements,
            "pvp_stats": self.pvp_stats,
            "element": self.element,
            "last_active": self.last_active,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data):
        player = cls(data["user_id"], data["username"], data["first_name"])
        for key, value in data.items():
            if hasattr(player, key):
                setattr(player, key, value)
        return player
    
    def get_effective_stats(self):
        effective_stats = self.stats.copy()
        
        # Apply equipment bonuses
        for item_slot, item_id in self.equipment.items():
            if item_id:
                item = get_item(item_id)
                if item and "stats" in item:
                    for stat, value in item["stats"].items():
                        if stat in effective_stats:
                            effective_stats[stat] += value
        
        # Apply skill bonuses
        for skill_id in self.skills:
            skill = get_skill(skill_id)
            if skill and "passive_effects" in skill:
                for effect in skill["passive_effects"]:
                    if effect["type"] == "stat_bonus" and effect["stat"] in effective_stats:
                        effective_stats[effect["stat"]] += effect["value"]
        
        return effective_stats
    
    async def can_use_skill(self, skill_id):
        skill = get_skill(skill_id)
        if not skill:
            return False
        
        # Check cooldown using MongoDB
        cooldown_data = cooldowns_col.find_one({
            "user_id": self.user_id,
            "type": f"skill_{skill_id}"
        })
        
        if cooldown_data and cooldown_data["expire_at"] > datetime.now():
            return False
        
        # Check MP cost
        if skill.get("mp_cost", 0) > self.stats["mp"]:
            return False
        
        # Check level requirement
        if skill.get("level_required", 1) > self.level:
            return False
        
        return True
    
    async def use_skill(self, skill_id):
        skill = get_skill(skill_id)
        if not skill or not await self.can_use_skill(skill_id):
            return False
        
        # Deduct MP
        self.stats["mp"] -= skill.get("mp_cost", 0)
        
        # Set cooldown in MongoDB
        cooldown_seconds = skill.get("cooldown", 0)
        if cooldown_seconds > 0:
            cooldowns_col.update_one(
                {
                    "user_id": self.user_id,
                    "type": f"skill_{skill_id}"
                },
                {
                    "$set": {
                        "expire_at": datetime.now() + timedelta(seconds=cooldown_seconds)
                    }
                },
                upsert=True
            )
        
        return True
    
    def level_up(self):
        exp_needed = self.level * 100
        if self.exp >= exp_needed:
            self.exp -= exp_needed
            self.level += 1
            
            # Increase stats on level up
            self.stats["max_hp"] += 10
            self.stats["max_mp"] += 5
            self.stats["attack"] += 2
            self.stats["defense"] += 1
            self.stats["magic"] += 1
            self.stats["speed"] += 0.5
            
            # Restore HP and MP
            self.stats["hp"] = self.stats["max_hp"]
            self.stats["mp"] = self.stats["max_mp"]
            
            return True
        return False
    
    def add_exp(self, amount):
        self.exp += amount
        leveled_up = False
        while self.level_up():
            leveled_up = True
        return leveled_up
    
    def heal(self, amount):
        self.stats["hp"] = min(self.stats["hp"] + amount, self.stats["max_hp"])
        return self.stats["hp"]
    
    def restore_mp(self, amount):
        self.stats["mp"] = min(self.stats["mp"] + amount, self.stats["max_mp"])
        return self.stats["mp"]

# Advanced Battle System
class AdvancedBattle:
    def __init__(self, battle_id, battle_type, participants, settings=None):
        self.battle_id = battle_id
        self.battle_type = battle_type
        self.participants = participants  # List of player IDs or teams
        self.settings = settings or {}
        self.turn_order = []
        self.current_turn_index = 0
        self.turn_count = 0
        self.log = []
        self.status = "waiting"  # waiting, ongoing, completed, cancelled
        self.start_time = None
        self.end_time = None
        self.winner = None
        self.environment = self._generate_environment()
    
    def _generate_environment(self):
        # Generate random battle environment with effects
        environments = [
            {"name": "Forest", "effects": [{"type": "healing", "value": 0.01}]},
            {"name": "Desert", "effects": [{"type": "burning", "value": 0.005}]},
            {"name": "Volcano", "effects": [{"type": "fire_damage_bonus", "value": 0.1}]},
            {"name": "Ocean", "effects": [{"type": "water_damage_bonus", "value": 0.1}]},
            {"name": "Sky Temple", "effects": [{"type": "mp_regen", "value": 0.01}]},
        ]
        return random.choice(environments)
    
    def to_dict(self):
        return {
            "battle_id": self.battle_id,
            "battle_type": self.battle_type,
            "participants": [p.to_dict() for p in self.participants],
            "settings": self.settings,
            "turn_order": [p.user_id for p in self.turn_order],
            "current_turn_index": self.current_turn_index,
            "turn_count": self.turn_count,
            "log": self.log,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "winner": self.winner.user_id if self.winner else None,
            "environment": self.environment
        }
    
    @classmethod
    def from_dict(cls, data):
        # Reconstruct participants from dict
        participants = []
        for p_data in data["participants"]:
            participants.append(AdvancedPlayer.from_dict(p_data))
        
        battle = cls(
            data["battle_id"],
            BattleType(data["battle_type"]),
            participants,
            data.get("settings", {})
        )
        
        # Reconstruct turn order from user IDs
        battle.turn_order = []
        for user_id in data["turn_order"]:
            for p in participants:
                if p.user_id == user_id:
                    battle.turn_order.append(p)
                    break
        
        battle.current_turn_index = data["current_turn_index"]
        battle.turn_count = data["turn_count"]
        battle.log = data["log"]
        battle.status = data["status"]
        battle.start_time = data["start_time"]
        battle.end_time = data["end_time"]
        
        # Reconstruct winner
        if data["winner"]:
            for p in participants:
                if p.user_id == data["winner"]:
                    battle.winner = p
                    break
        
        battle.environment = data["environment"]
        return battle
    
    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {message}")
        if len(self.log) > 20:  # Keep only last 20 log entries
            self.log.pop(0)
    
    def start_battle(self):
        self.status = "ongoing"
        self.start_time = datetime.now()
        
        # Determine turn order based on speed stats
        self.turn_order = sorted(
            self.participants,
            key=lambda p: p.get_effective_stats()["speed"],
            reverse=True
        )
        
        self.add_log(f"Battle started in {self.environment['name']}!")
        for effect in self.environment["effects"]:
            self.add_log(f"Environment effect: {effect['type']}")
    
    def get_current_player(self):
        if not self.turn_order:
            return None
        return self.turn_order[self.current_turn_index]
    
    def next_turn(self):
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        self.turn_count += 1
        
        # Apply environment effects at the start of each turn
        current_player = self.get_current_player()
        if current_player:
            for effect in self.environment["effects"]:
                self.apply_environment_effect(current_player, effect)
    
    def apply_environment_effect(self, player, effect):
        stats = player.stats
        if effect["type"] == "healing":
            heal_amount = stats["max_hp"] * effect["value"]
            player.heal(heal_amount)
            self.add_log(f"{player.first_name} healed {heal_amount:.1f} HP from environment")
        elif effect["type"] == "burning":
            damage = stats["max_hp"] * effect["value"]
            player.stats["hp"] -= damage
            self.add_log(f"{player.first_name} took {damage:.1f} damage from environment")
        elif effect["type"] == "mp_regen":
            mp_restore = stats["max_mp"] * effect["value"]
            player.restore_mp(mp_restore)
            self.add_log(f"{player.first_name} restored {mp_restore:.1f} MP from environment")
    
    def check_battle_end(self):
        # Check if battle should end (only one team/player left)
        alive_players = [p for p in self.participants if p.stats["hp"] > 0]
        
        if len(alive_players) <= 1:
            self.status = "completed"
            self.end_time = datetime.now()
            
            if alive_players:
                self.winner = alive_players[0]
                self.add_log(f"{self.winner.first_name} wins the battle!")
            else:
                self.add_log("The battle ended in a draw!")
            
            return True
        return False

# Guild System
class Guild:
    def __init__(self, guild_id, name, creator_id):
        self.guild_id = guild_id
        self.name = name
        self.creator_id = creator_id
        self.members = [creator_id]
        self.level = 1
        self.exp = 0
        self.treasury = 0
        self.skills = []
        self.announcement = ""
        self.created_at = datetime.now()
    
    def to_dict(self):
        return {
            "guild_id": self.guild_id,
            "name": self.name,
            "creator_id": self.creator_id,
            "members": self.members,
            "level": self.level,
            "exp": self.exp,
            "treasury": self.treasury,
            "skills": self.skills,
            "announcement": self.announcement,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data):
        guild = cls(data["guild_id"], data["name"], data["creator_id"])
        guild.members = data["members"]
        guild.level = data["level"]
        guild.exp = data["exp"]
        guild.treasury = data["treasury"]
        guild.skills = data["skills"]
        guild.announcement = data["announcement"]
        guild.created_at = data["created_at"]
        return guild
    
    def add_member(self, user_id):
        if user_id not in self.members:
            self.members.append(user_id)
            return True
        return False
    
    def remove_member(self, user_id):
        if user_id in self.members:
            self.members.remove(user_id)
            return True
        return False
    
    def add_exp(self, amount):
        self.exp += amount
        exp_needed = self.level * 1000
        if self.exp >= exp_needed:
            self.exp -= exp_needed
            self.level += 1
            return True
        return False

# Database operations
async def get_player(user_id: int, username: str = "", first_name: str = ""):
    player_data = players_col.find_one({"user_id": user_id})
    if player_data:
        return AdvancedPlayer.from_dict(player_data)
    else:
        new_player = AdvancedPlayer(user_id, username, first_name)
        players_col.insert_one(new_player.to_dict())
        return new_player

async def update_player(player: AdvancedPlayer):
    players_col.update_one(
        {"user_id": player.user_id},
        {"$set": player.to_dict()}
    )

async def create_battle(battle_id: str, battle_type: BattleType, participants: list, settings: dict = None):
    battle = AdvancedBattle(battle_id, battle_type, participants, settings)
    battles_col.insert_one(battle.to_dict())
    return battle

async def get_battle(battle_id: str):
    battle_data = battles_col.find_one({"battle_id": battle_id})
    if battle_data:
        return AdvancedBattle.from_dict(battle_data)
    return None

async def update_battle(battle: AdvancedBattle):
    battles_col.update_one(
        {"battle_id": battle.battle_id},
        {"$set": battle.to_dict()}
    )

async def delete_battle(battle_id: str):
    battles_col.delete_one({"battle_id": battle_id})

async def create_guild(guild_id: str, name: str, creator_id: int):
    guild = Guild(guild_id, name, creator_id)
    guilds_col.insert_one(guild.to_dict())
    return guild

async def get_guild(guild_id: str):
    guild_data = guilds_col.find_one({"guild_id": guild_id})
    if guild_data:
        return Guild.from_dict(guild_data)
    return None

async def update_guild(guild: Guild):
    guilds_col.update_one(
        {"guild_id": guild.guild_id},
        {"$set": guild.to_dict()}
    )

# Item and skill data (would typically be in a separate file)
def get_item(item_id):
    # This would query your items database
    items = {
        "wooden_sword": {
            "name": "Wooden Sword",
            "type": "weapon",
            "rarity": "common",
            "stats": {"attack": 5},
            "requirements": {"level": 1}
        },
        "iron_armor": {
            "name": "Iron Armor",
            "type": "armor",
            "rarity": "uncommon",
            "stats": {"defense": 8, "speed": -1},
            "requirements": {"level": 5}
        }
    }
    return items.get(item_id)

def get_skill(skill_id):
    # This would query your skills database
    skills = {
        "fireball": {
            "name": "Fireball",
            "element": "fire",
            "mp_cost": 10,
            "cooldown": 3,
            "damage": 15,
            "description": "Launches a fiery projectile at the enemy"
        },
        "heal": {
            "name": "Heal",
            "element": "light",
            "mp_cost": 15,
            "cooldown": 4,
            "healing": 20,
            "description": "Restores HP to yourself or an ally"
        }
    }
    return skills.get(skill_id)

# Helper function for health bars
def create_health_bar(percentage, length=10):
    filled = int(percentage * length)
    return "█" * filled + "░" * (length - filled)

# Battle actions with advanced mechanics
async def handle_advanced_battle_action(client, callback_query: CallbackQuery, action: str, target_id: str = None):
    user_id = callback_query.from_user.id
    battle_id = callback_query.data.split("_")[-1]
    
    battle = await get_battle(battle_id)
    if not battle or battle.status != "ongoing":
        await callback_query.answer("This battle has ended or doesn't exist!")
        return
    
    current_player = battle.get_current_player()
    if not current_player or current_player.user_id != user_id:
        await callback_query.answer("It's not your turn!")
        return
    
    # Handle different actions
    if action == "attack":
        # Basic attack
        if not target_id:
            await callback_query.answer("No target specified!")
            return
        
        target = None
        for p in battle.participants:
            if p.user_id == int(target_id):
                target = p
                break
        
        if not target or target.stats["hp"] <= 0:
            await callback_query.answer("Invalid target!")
            return
        
        damage, is_critical = calculate_damage(current_player, target, "physical")
        target.stats["hp"] -= damage
        battle.add_log(f"{current_player.first_name} attacks {target.first_name} for {damage} damage! {'(Critical!)' if is_critical else ''}")
        
        # Update player stats
        current_player.pvp_stats["damage_dealt"] += damage
        target.pvp_stats["damage_taken"] += damage
        
        # Move to next turn
        battle.next_turn()
        
    elif action == "skill":
        # Use a skill
        skill_id = target_id  # In this case, target_id is the skill ID
        if not await current_player.can_use_skill(skill_id):
            await callback_query.answer("Cannot use this skill now!")
            return
        
        skill = get_skill(skill_id)
        if not skill:
            await callback_query.answer("Invalid skill!")
            return
        
        # Use the skill
        await current_player.use_skill(skill_id)
        
        # Handle different skill types
        if skill_id == "fireball":
            # For simplicity, target the first available opponent
            for target in battle.participants:
                if target != current_player and target.stats["hp"] > 0:
                    damage, is_critical = calculate_damage(current_player, target, "magical")
                    target.stats["hp"] -= damage
                    battle.add_log(f"{current_player.first_name} casts Fireball on {target.first_name} for {damage} damage! {'(Critical!)' if is_critical else ''}")
                    break
        
        elif skill_id == "heal":
            # Heal self
            heal_amount = skill.get("healing", 0)
            current_player.heal(heal_amount)
            battle.add_log(f"{current_player.first_name} heals for {heal_amount} HP!")
        
        # Move to next turn
        battle.next_turn()
    
    elif action == "flee":
        # Try to flee from battle
        flee_chance = current_player.stats["speed"] / (current_player.stats["speed"] + 50)
        if random.random() < flee_chance:
            battle.status = "fled"
            battle.add_log(f"{current_player.first_name} fled from battle!")
            # Penalty for fleeing
            current_player.stats["gold"] = max(0, current_player.stats["gold"] - 20)
        else:
            battle.add_log(f"{current_player.first_name} failed to flee!")
            # Move to next turn even if failed to flee
            battle.next_turn()
    
    # Check if battle is over
    if battle.check_battle_end():
        # Award rewards
        if battle.winner:
            battle.winner.add_exp(50)
            battle.winner.stats["gold"] += 30
            battle.winner.pvp_stats["wins"] += 1
            
            # Count kills
            for player in battle.participants:
                if player != battle.winner and player.stats["hp"] <= 0:
                    battle.winner.pvp_stats["kills"] += 1
            
            # Update winner in database
            await update_player(battle.winner)
        
        # Update all participants
        for player in battle.participants:
            if player != battle.winner:
                player.pvp_stats["losses"] += 1
                if player.stats["hp"] <= 0:
                    player.pvp_stats["deaths"] += 1
                player.add_exp(10)
                player.stats["gold"] += 10
                await update_player(player)
    
    # Update battle in database
    await update_battle(battle)
    
    # Send updated battle message
    await send_advanced_battle_message(client, callback_query.message.chat.id, battle)
    await callback_query.answer()

def calculate_damage(attacker, defender, damage_type="physical"):
    attacker_stats = attacker.get_effective_stats()
    defender_stats = defender.get_effective_stats()
    
    base_damage = 0
    if damage_type == "physical":
        base_damage = attacker_stats["attack"] * (1 + random.random() * 0.2)  # 0-20% random variation
        defense = defender_stats["defense"]
    elif damage_type == "magical":
        base_damage = attacker_stats["magic"] * (1 + random.random() * 0.2)
        defense = defender_stats["defense"] * 0.5  # Magic ignores 50% of defense
    
    # Elemental advantages/disadvantages
    element_multiplier = calculate_element_multiplier(attacker.element, defender.element)
    base_damage *= element_multiplier
    
    # Critical hit chance (based on speed)
    crit_chance = attacker_stats["speed"] / 100
    is_critical = random.random() < crit_chance
    if is_critical:
        base_damage *= 1.5
    
    # Calculate final damage
    damage = max(1, base_damage - defense * 0.5)
    
    return int(damage), is_critical

def calculate_element_multiplier(attacker_element, defender_element):
    # Element advantage system
    advantages = {
        Element.FIRE.value: [Element.EARTH.value, Element.AIR.value],
        Element.WATER.value: [Element.FIRE.value, Element.EARTH.value],
        Element.EARTH.value: [Element.WATER.value, Element.AIR.value],
        Element.AIR.value: [Element.EARTH.value, Element.WATER.value],
        Element.LIGHT.value: [Element.DARK.value],
        Element.DARK.value: [Element.LIGHT.value]
    }
    
    if defender_element in advantages.get(attacker_element, []):
        return 1.5  # Advantage
    elif attacker_element in advantages.get(defender_element, []):
        return 0.7  # Disadvantage
    else:
        return 1.0  # Neutral

async def send_advanced_battle_message(client, chat_id, battle):
    # Create a detailed battle status message
    message = f"⚔️ **{battle.battle_type.value.upper()} BATTLE** ⚔️\n\n"
    message += f"**Environment:** {battle.environment['name']}\n\n"
    
    # Add participant status
    for i, player in enumerate(battle.participants):
        status_icon = "❤️" if player.stats["hp"] > 0 else "💀"
        hp_percent = player.stats["hp"] / player.stats["max_hp"]
        hp_bar = create_health_bar(hp_percent)
        
        message += (
            f"{status_icon} **{player.first_name}** (Lv.{player.level}) "
            f"{'(Current Turn)' if battle.get_current_player() == player else ''}\n"
            f"HP: {hp_bar} {player.stats['hp']}/{player.stats['max_hp']}\n"
            f"MP: {player.stats['mp']}/{player.stats['max_mp']}\n\n"
        )
    
    # Add battle log
    message += "**Battle Log:**\n" + "\n".join(battle.log[-5:])
    
    # Create appropriate action buttons
    if battle.status == "ongoing":
        current_player = battle.get_current_player()
        keyboard = []
        
        # Attack options
        attack_row = []
        for target in battle.participants:
            if target != current_player and target.stats["hp"] > 0:
                attack_row.append(
                    InlineKeyboardButton(
                        f"🗡 {target.first_name}",
                        callback_data=f"battle_attack_{target.user_id}_{battle.battle_id}"
                    )
                )
        if attack_row:
            keyboard.append(attack_row)
        
        # Skill options
        skill_row = []
        for skill_id in current_player.skills:
            skill = get_skill(skill_id)
            if skill and await current_player.can_use_skill(skill_id):
                skill_row.append(
                    InlineKeyboardButton(
                        f"🔥 {skill['name']}",
                        callback_data=f"battle_skill_{skill_id}_{battle.battle_id}"
                    )
                )
        if skill_row:
            keyboard.append(skill_row)
        
        # Item and flee options
        keyboard.append([
            InlineKeyboardButton("🎒 Items", callback_data=f"battle_items_{battle.battle_id}"),
            InlineKeyboardButton("🏃 Flee", callback_data=f"battle_flee_{battle.battle_id}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
    else:
        # Battle ended
        if battle.winner:
            message += f"\n\n**Winner: {battle.winner.first_name}!**"
        else:
            message += "\n\n**The battle ended in a draw!**"
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Stats", callback_data=f"battle_stats_{battle.battle_id}")],
            [InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch_{battle.battle_id}")]
        ])
    
    # Send or edit message
    try:
        await client.send_message(
            chat_id,
            message,
            reply_markup=reply_markup
        )
    except:
        # If message exists, edit it
        pass

# Command handlers for advanced features
@app.on_message(filters.command("sgrt"))
async def start_command(client, message: Message):
    user = message.from_user
    player = await get_player(user.id, user.username, user.first_name)
    
    welcome_text = (
        "🎮 **Advanced PvP Battle Game** 🎮\n\n"
        "Challenge other players to epic battles with advanced RPG mechanics!\n\n"
        "**Available Commands:**\n"
        "/battle @username - Challenge a player\n"
        "/profile - View your profile\n"
        "/leaderboard - View top players\n"
        "/guild - Guild management\n"
        "/skills - View and manage skills\n\n"
        "**Features:**\n"
        "• Elemental combat system\n"
        "• Skill-based battles with cooldowns\n"
        "• Guild system with shared benefits\n"
        "• Equipment and inventory management\n"
        "• Daily quests and achievements\n\n"
        "Start by challenging someone with /battle @username!"
    )
    
    await message.reply_text(welcome_text)

@app.on_message(filters.command("profille"))
async def profile_command(client, message: Message):
    user = message.from_user
    player = await get_player(user.id, user.username, user.first_name)
    
    effective_stats = player.get_effective_stats()
    
    profile_text = (
        f"👤 **{player.first_name}'s Profile**\n"
        f"**Title:** {player.title}\n"
        f"**Level:** {player.level}\n"
        f"**EXP:** {player.exp}/{player.level * 100}\n"
        f"**Element:** {player.element.capitalize()}\n\n"
        f"**Stats:**\n"
        f"• HP: {player.stats['hp']}/{player.stats['max_hp']}\n"
        f"• MP: {player.stats['mp']}/{player.stats['max_mp']}\n"
        f"• Attack: {effective_stats['attack']}\n"
        f"• Defense: {effective_stats['defense']}\n"
        f"• Magic: {effective_stats['magic']}\n"
        f"• Speed: {effective_stats['speed']}\n\n"
        f"**Economy:**\n"
        f"• Gold: {player.stats['gold']}\n"
        f"• Gems: {player.stats['gems']}\n\n"
        f"**PvP Stats:**\n"
        f"• Wins: {player.pvp_stats['wins']}\n"
        f"• Losses: {player.pvp_stats['losses']}\n"
        f"• Kills: {player.pvp_stats['kills']}\n"
        f"• Deaths: {player.pvp_stats['deaths']}\n"
        f"• Damage Dealt: {player.pvp_stats['damage_dealt']}\n"
        f"• Damage Taken: {player.pvp_stats['damage_taken']}\n"
    )
    
    if player.guild_id:
        guild = await get_guild(player.guild_id)
        if guild:
            profile_text += f"\n**Guild:** {guild.name} ({player.guild_role})"
    
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
    if opponent.stats["hp"] <= 0:
        await message.reply_text(f"{opponent.first_name} is too weak to battle! They need to heal first.")
        return
    
    # Create battle
    battle_id = f"{challenger.user_id}_{opponent.user_id}_{datetime.now().timestamp()}"
    battle = await create_battle(battle_id, BattleType.DUEL, [challenger, opponent])
    
    # Start the battle
    battle.start_battle()
    await update_battle(battle)
    
    # Send battle message
    await send_advanced_battle_message(client, message.chat.id, battle)
    
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
    # Get top 10 players by victories
    top_players = players_col.find().sort("pvp_stats.wins", -1).limit(10)
    
    leaderboard_text = "🏆 **Top Players by Wins** 🏆\n\n"
    
    for i, player_data in enumerate(top_players):
        player = AdvancedPlayer.from_dict(player_data)
        leaderboard_text += f"{i+1}. {player.first_name} - {player.pvp_stats['wins']} wins (Lv.{player.level})\n"
    
    await message.reply_text(leaderboard_text)

@app.on_message(filters.command("guild"))
async def guild_command(client, message: Message):
    subcommand = message.command[1] if len(message.command) > 1 else "info"
    
    if subcommand == "create" and len(message.command) > 2:
        guild_name = message.command[2]
        player = await get_player(message.from_user.id, message.from_user.username, message.from_user.first_name)
        
        # Check if player is already in a guild
        if player.guild_id:
            await message.reply_text("You're already in a guild!")
            return
        
        # Create new guild
        guild_id = f"guild_{datetime.now().timestamp()}"
        guild = await create_guild(guild_id, guild_name, player.user_id)
        
        # Add player to guild
        player.guild_id = guild_id
        player.guild_role = "leader"
        await update_player(player)
        
        await message.reply_text(f"Guild '{guild_name}' created successfully!")
    
    elif subcommand == "join" and len(message.command) > 2:
        guild_name = message.command[2]
        player = await get_player(message.from_user.id, message.from_user.username, message.from_user.first_name)
        
        # Find guild by name
        guild_data = guilds_col.find_one({"name": guild_name})
        if not guild_data:
            await message.reply_text("Guild not found!")
            return
        
        guild = Guild.from_dict(guild_data)
        
        # Add player to guild
        if guild.add_member(player.user_id):
            player.guild_id = guild.guild_id
            player.guild_role = "member"
            await update_player(player)
            await update_guild(guild)
            
            await message.reply_text(f"You've joined the guild '{guild_name}'!")
        else:
            await message.reply_text("You're already in this guild!")
    
    elif subcommand == "info":
        player = await get_player(message.from_user.id, message.from_user.username, message.from_user.first_name)
        
        if not player.guild_id:
            await message.reply_text("You're not in a guild!")
            return
        
        guild = await get_guild(player.guild_id)
        if not guild:
            await message.reply_text("Guild not found!")
            return
        
        # Get guild members
        members = []
        for member_id in guild.members:
            member_data = players_col.find_one({"user_id": member_id})
            if member_data:
                member = AdvancedPlayer.from_dict(member_data)
                members.append(member)
        
        guild_info = (
            f"🏰 **Guild: {guild.name}** (Level {guild.level})\n\n"
            f"**Members:** {len(guild.members)}/20\n"
            f"**EXP:** {guild.exp}/{guild.level * 1000}\n"
            f"**Treasury:** {guild.treasury} gold\n\n"
            f"**Announcement:**\n{guild.announcement}\n\n"
            f"**Members:**\n"
        )
        
        for member in sorted(members, key=lambda m: m.level, reverse=True)[:10]:
            guild_info += f"• {member.first_name} (Lv.{member.level})\n"
        
        if len(members) > 10:
            guild_info += f"... and {len(members) - 10} more"
        
        await message.reply_text(guild_info)

# Callback query handlers
@app.on_callback_query(filters.regex("^battle_"))
async def battle_callback_handler(client, callback_query: CallbackQuery):
    data_parts = callback_query.data.split("_")
    action = data_parts[1]
    
    if len(data_parts) >= 4:
        target_id = data_parts[2]
        battle_id = data_parts[3]
        await handle_advanced_battle_action(client, callback_query, action, target_id)
    else:
        await callback_query.answer("Invalid action!")

@app.on_callback_query(filters.regex("^rematch_"))
async def rematch_callback_handler(client, callback_query: CallbackQuery):
    battle_id = callback_query.data.split("_")[1]
    
    battle = await get_battle(battle_id)
    if not battle:
        await callback_query.answer("Battle not found!")
        return
    
    # Check if all players are still available and have enough HP
    for player in battle.participants:
        if player.stats["hp"] <= 0:
            await callback_query.answer(f"{player.first_name} is too weak to battle!", show_alert=True)
            return
    
    # Create new battle with same participants
    new_battle_id = f"rematch_{battle_id}_{datetime.now().timestamp()}"
    new_battle = await create_battle(new_battle_id, battle.battle_type, battle.participants, battle.settings)
    
    # Start the battle
    new_battle.start_battle()
    await update_battle(new_battle)
    
    # Send new battle message
    await send_advanced_battle_message(client, callback_query.message.chat.id, new_battle)
    await callback_query.answer()

