import asyncio
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import feedparser
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient, DESCENDING
from pymongo.errors import DuplicateKeyError
from wallbot import wbot as app
from config import DB_URL


# Configuration
CHECK_INTERVAL = 300  # Seconds between RSS checks (5 minutes)
MAX_POSTS_PER_CHECK = 5  # Max new posts to send per feed per check
MAX_ENTRY_AGE = 7  # Days (ignore entries older than this)
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", 784589736))  # Your Telegram user ID

# Initialize MongoDB Client")
mongo_client = MongoClient(DB_URL)
db = mongo_client.rss_bot

# Collections
feeds_col = db.feeds
subscriptions_col = db.subscriptions
sent_entries_col = db.sent_entries
groups_col = db.groups

# Database indexes
feeds_col.create_index("url", unique=True)
subscriptions_col.create_index([("feed_id", 1), ("group_id", 1)], unique=True)
sent_entries_col.create_index("entry_id", unique=True)

# ======================
# HELPER FUNCTIONS
# ======================

def generate_entry_id(entry):
    """Create unique ID for an entry"""
    return entry.get("id") or entry.get("link") or hash(entry.get("title", ""))
  
def is_valid_url(url):
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def format_entry(entry):
    """Format RSS entry for Telegram"""
    title = entry.get("title", "No title")
    link = entry.get("link", "")
    published = entry.get("published", "")
    summary = entry.get("summary", "")
    
    # Clean HTML tags
    summary = re.sub(r'<[^>]+>', '', summary)
    
    # Truncate long summaries
    if len(summary) > 1000:
        summary = summary[:1000] + "..."
    
    # Format date if available
    if hasattr(entry, "published_parsed"):
        pub_date = datetime(*entry.published_parsed[:6])
        published = pub_date.strftime("%Y-%m-%d %H:%M")
    
    message = (
        f"**{title}**\n"
        f"_{published}_\n\n"
        f"{summary}\n\n"
        f"[Read more]({link})"
    )
    
    # Add image if available
    image_url = None
    if "media_content" in entry and entry.media_content:
        image_url = entry.media_content[0]["url"]
    elif "enclosures" in entry and entry.enclosures:
        for enc in entry.enclosures:
            if enc.type.startswith("image/"):
                image_url = enc.href
                break
    elif "image" in entry and "href" in entry.image:
        image_url = entry.image.href
    
    return message, image_url

# ======================
# DATABASE OPERATIONS
# ======================

async def add_feed(url: str, title: str = ""):
    """Add new feed to database"""
    if not is_valid_url(url):
        return False, "Invalid URL format"
    
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            return False, "No entries found in feed"
            
        title = title or feed.feed.get("title", url)
        result = feeds_col.insert_one({
            "url": url,
            "title": title,
            "last_checked": datetime.min,
            "created_at": datetime.now()
        })
        return True, f"✅ Feed added: {title} (ID: {result.inserted_id})"
    except DuplicateKeyError:
        return False, "⚠️ Feed already exists"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

async def remove_feed(feed_id: str):
    """Remove feed and its subscriptions"""
    result = feeds_col.delete_one({"_id": feed_id})
    if result.deleted_count:
        subscriptions_col.delete_many({"feed_id": feed_id})
        return True, "🗑️ Feed removed"
    return False, "❌ Feed not found"

async def subscribe_group(feed_id: str, group_id: int, group_title: str):
    """Subscribe group to feed"""
    try:
        subscriptions_col.insert_one({
            "feed_id": feed_id,
            "group_id": group_id,
            "group_title": group_title,
            "subscribed_at": datetime.now()
        })
        groups_col.update_one(
            {"group_id": group_id},
            {"$set": {"title": group_title}},
            upsert=True
        )
        return True, "✅ Subscribed to feed"
    except DuplicateKeyError:
        return False, "⚠️ Already subscribed"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

async def unsubscribe_group(feed_id: str, group_id: int):
    """Unsubscribe group from feed"""
    result = subscriptions_col.delete_one({
        "feed_id": feed_id,
        "group_id": group_id
    })
    if result.deleted_count:
        return True, "✅ Unsubscribed from feed"
    return False, "❌ Subscription not found"

async def get_feeds():
    """Get all feeds"""
    return list(feeds_col.find().sort("title", 1))

async def get_group_subscriptions(group_id: int):
    """Get all subscriptions for a group"""
    return list(subscriptions_col.find({"group_id": group_id}))

async def get_feed_subscriptions(feed_id: str):
    """Get all groups subscribed to a feed"""
    return list(subscriptions_col.find({"feed_id": feed_id}))

async def mark_entry_sent(feed_id: str, entry_id: str):
    """Mark entry as sent"""
    sent_entries_col.update_one(
        {"entry_id": entry_id},
        {"$set": {"feed_id": feed_id, "sent_at": datetime.now()}},
        upsert=True
    )

async def is_entry_sent(entry_id: str):
    """Check if entry was already sent"""
    return bool(sent_entries_col.find_one({"entry_id": entry_id}))

async def update_feed_last_checked(feed_id: str):
    """Update last checked timestamp"""
    feeds_col.update_one(
        {"_id": feed_id},
        {"$set": {"last_checked": datetime.now()}}
    )



@app.on_message(filters.command("addfeed") & filters.user(ADMIN_USER_ID))
async def add_feed_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /addfeed [RSS URL]")
        return
    
    url = message.text.split(maxsplit=1)[1].strip()
    success, response = await add_feed(url)
    await message.reply_text(response)

@app.on_message(filters.command("removefeed") & filters.user(ADMIN_USER_ID))
async def remove_feed_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /removefeed [feed_id]")
        return
    
    feed_id = message.command[1]
    success, response = await remove_feed(feed_id)
    await message.reply_text(response)

@app.on_message(filters.command("listfeeds"))
async def list_feeds_cmd(client: Client, message: Message):
    feeds = await get_feeds()
    if not feeds:
        await message.reply_text("No feeds configured")
        return
    
    response = "📋 **Configured Feeds**\n\n"
    for feed in feeds:
        subs = await get_feed_subscriptions(feed["_id"])
        response += (
            f"ID: `{feed['_id']}`\n"
            f"Title: {feed['title']}\n"
            f"URL: {feed['url']}\n"
            f"Groups: {len(subs)}\n\n"
        )
    
    await message.reply_text(response)

@app.on_message(filters.command("sub") & filters.group)
async def subscribe_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /sub [feed_id]")
        return
    
    feed_id = message.command[1]
    group_id = message.chat.id
    group_title = message.chat.title
    
    success, response = await subscribe_group(
        feed_id, group_id, group_title
    )
    await message.reply_text(response)

@app.on_message(filters.command("unsub") & filters.group)
async def unsubscribe_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /unsub [feed_id]")
        return
    
    feed_id = message.command[1]
    group_id = message.chat.id
    
    success, response = await unsubscribe_group(feed_id, group_id)
    await message.reply_text(response)

@app.on_message(filters.command("listsubs") & filters.group)
async def list_subs_cmd(client: Client, message: Message):
    group_id = message.chat.id
    subs = await get_group_subscriptions(group_id)
    
    if not subs:
        await message.reply_text("❌ This group has no subscriptions")
        return
    
    response = "📋 **Group Subscriptions**\n\n"
    for sub in subs:
        feed = feeds_col.find_one({"_id": sub["feed_id"]})
        if feed:
            response += f"ID: `{sub['feed_id']}`\nTitle: {feed['title']}\nURL: {feed['url']}\n\n"
    
    await message.reply_text(response)

@app.on_message(filters.command("forcecheck") & filters.user(ADMIN_USER_ID))
async def force_check_cmd(client: Client, message: Message):
    await message.reply_text("⏳ Checking feeds...")
    await check_feeds()
    await message.reply_text("✅ Feed check completed")

# ======================
# RSS PROCESSING
# ======================

async def send_to_group(group_id: int, message: str, image_url: str = None):
    """Send message to Telegram group"""
    try:
        if image_url:
            await app.send_photo(
                chat_id=group_id,
                photo=image_url,
                caption=message,
                parse_mode="markdown"
            )
        else:
            await app.send_message(
                chat_id=group_id,
                text=message,
                parse_mode="markdown",
                disable_web_page_preview=False
            )
        return True
    except Exception as e:
        print(f"Error sending to group {group_id}: {str(e)}")
        return False

async def process_feed(feed):
    """Process a single RSS feed"""
    try:
        feed_id = str(feed["_id"])
        feed_url = feed["url"]
        feed_title = feed["title"]
        
        parsed_feed = feedparser.parse(feed_url)
        if not parsed_feed.entries:
            print(f"No entries in feed: {feed_url}")
            return False
        
        # Process entries from newest to oldest
        entries = sorted(
            parsed_feed.entries,
            key=lambda x: x.get("published_parsed", (0,)),
            reverse=True
        )
        
        sent_count = 0
        for entry in entries:
            if sent_count >= MAX_POSTS_PER_CHECK:
                break
                
            # Generate unique ID for entry
            entry_id = generate_entry_id(entry)
            if not entry_id:
                continue
                
            # Skip if already sent
            if await is_entry_sent(entry_id):
                continue
                
            # Skip entries older than MAX_ENTRY_AGE days
            if hasattr(entry, "published_parsed"):
                pub_date = datetime(*entry.published_parsed[:6])
                if (datetime.now() - pub_date).days > MAX_ENTRY_AGE:
                    continue
            
            # Format and send message
            message_text, image_url = format_entry(entry)
            groups = await get_feed_subscriptions(feed_id)
            
            # Send to all subscribed groups
            for group in groups:
                group_id = group["group_id"]
                success = await send_to_group(group_id, message_text, image_url)
                if success:
                    print(f"Sent to group {group_id}: {entry_id}")
            
            # Mark as sent
            await mark_entry_sent(feed_id, entry_id)
            sent_count += 1
            
            # Short delay to avoid flooding
            await asyncio.sleep(1)
        
        # Update last checked time
        await update_feed_last_checked(feed_id)
        return True
        
    except Exception as e:
        print(f"Error processing feed {feed_url}: {str(e)}")
        return False

async def check_feeds():
    """Check all feeds for new entries"""
    feeds = await get_feeds()
    if not feeds:
        return
    
    print(f"\nChecking {len(feeds)} feeds at {datetime.now().isoformat()}")
    
    for feed in feeds:
        print(f"Processing feed: {feed['title']}")
        await process_feed(feed)
        await asyncio.sleep(2)  # Delay between feeds

# ======================
# BACKGROUND TASK
# ======================

async def feed_checker():
    """Periodic feed checking task"""
    print("RSS Feed Bot started")
    while True:
        try:
            await check_feeds()
        except Exception as e:
            print(f"Error in feed checker: {str(e)}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ======================
# STARTUP
# ======================

async def main():
    """Main async function"""
    await app.start()
    print("Bot started")
    asyncio.create_task(feed_checker())
    
    # Keep the application running
    while True:
        await asyncio.sleep(3600)  # Sleep for 1 hour

if __name__ == "__main__":
    # Create event loop
    loop = asyncio.get_event_loop()
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Stopping bot...")
    finally:
        loop.run_until_complete(app.stop())
        loop.close()
