# enums.py
from enum import Enum


class ParseMode(Enum):
    """Defines allowed parse modes for Pyrogram messages."""
    MARKDOWN = "markdown"
    MARKDOWN_V2 = "markdownv2"
    HTML = "html"
    NONE = None


class PunishmentType(Enum):
    """Types of punishments for moderation bots."""
    WARN = "warn"
    KICK = "kick"
    BAN = "ban"
    MUTE = "mute"
    TEMP_BAN = "temp_ban"
    TEMP_MUTE = "temp_mute"


class GameMode(Enum):
    """Game difficulty or mode (for game bots)."""
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    EXTREME = "extreme"


class Role(Enum):
    """User roles for advanced bots."""
    ADMIN = "admin"
    MEMBER = "member"
    BOT = "bot"
    CREATOR = "creator"


class LogLevel(Enum):
    """Logging levels used across the bot."""
    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
