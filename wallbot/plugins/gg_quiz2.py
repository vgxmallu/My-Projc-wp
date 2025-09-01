"""
Advanced Quiz Group Bot (Pyrogram)
Features:
- Group-play: one active quiz session per group (anyone can answer)
- First-correct scoring (fastest finger)
- Per-group leaderboard + global leaderboard
- User profiles (points, correct/wrong, streaks, best streak)
- Admin commands: /addq, /seed (loads embedded 100+ questions), /import (JSON text)
- Lifelines per user (50-50) and cooldowns
- Timed questions with scheduler
- MongoDB persistence

Environment variables required:
- BOT_TOKEN, API_ID, API_HASH, MONGO_URI
Optional: DB_NAME (default: quiz_bot), ADMIN_IDS (comma-separated ints)

Run: python advanced_quiz_group_bot.py
"""

import os
import logging
import random
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pymongo import MongoClient, ASCENDING, DESCENDING
from config import DB_URL
from wallbot import wbot as app
# ---------------- Config ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("adv_quiz_bot")


DB_NAME = "quiz_bot"
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS","784589736").split(",") if x.strip().isdigit()}


# ------------ DB setup ----------------
mongo = MongoClient(DB_URL)
db = mongo[DB_NAME]
users = db.users
questions = db.questions
sessions = db.sessions
group_scores = db.group_scores

# indexes
users.create_index([("user_id", ASCENDING)], unique=True)
questions.create_index([("category", ASCENDING), ("difficulty", ASCENDING)])
sessions.create_index([("session_id", ASCENDING)], unique=True)
group_scores.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)

# ------------ Constants --------------
QUESTION_TIMEOUT = 18  # seconds
POINTS_BASE = {"easy": 8, "medium": 12, "hard": 18}
FAST_BONUS = 2
STREAK_BONUS = 1
MAX_OPTIONS = 6
SESSION_COOLDOWN = 3  # seconds between questions to avoid spam

# ------------ Embedded question bank (100 questions) ------------
# Format: {"q":..., "options": [...], "answer": index, "category": ..., "difficulty": ...}
QUESTIONS = [
    {"q":"What is the capital of France?","options":["Paris","London","Berlin","Madrid"],"answer":0,"category":"Geography","difficulty":"easy"},
    {"q":"Who developed the theory of relativity?","options":["Newton","Einstein","Galileo","Tesla"],"answer":1,"category":"Science","difficulty":"medium"},
    {"q":"Which planet is known as the Red Planet?","options":["Venus","Mars","Jupiter","Saturn"],"answer":1,"category":"Space","difficulty":"easy"},
    {"q":"In computing, what does CPU stand for?","options":["Central Process Unit","Central Processing Unit","Computer Personal Unit","Control Processing Unit"],"answer":1,"category":"Technology","difficulty":"easy"},
    {"q":"What is the smallest prime number?","options":["0","1","2","3"],"answer":2,"category":"Math","difficulty":"easy"},
    {"q":"Which element has the chemical symbol O?","options":["Gold","Oxygen","Osmium","Iron"],"answer":1,"category":"Chemistry","difficulty":"easy"},
    {"q":"Who painted the Mona Lisa?","options":["Michelangelo","Da Vinci","Picasso","Rembrandt"],"answer":1,"category":"Art","difficulty":"medium"},
    {"q":"What is the largest mammal in the world?","options":["Elephant","Blue Whale","Giraffe","Orca"],"answer":1,"category":"Nature","difficulty":"easy"},
    {"q":"Which year did World War II end?","options":["1940","1942","1945","1950"],"answer":2,"category":"History","difficulty":"medium"},
    {"q":"What is the square root of 144?","options":["10","11","12","13"],"answer":2,"category":"Math","difficulty":"easy"},
    {"q":"Which gas do plants absorb from the atmosphere?","options":["Oxygen","Carbon Dioxide","Nitrogen","Hydrogen"],"answer":1,"category":"Biology","difficulty":"easy"},
    {"q":"Who wrote 'Romeo and Juliet'?","options":["Charles Dickens","William Shakespeare","Leo Tolstoy","Mark Twain"],"answer":1,"category":"Literature","difficulty":"easy"},
    {"q":"What is H2O commonly known as?","options":["Oxygen","Hydrogen","Water","Helium"],"answer":2,"category":"Chemistry","difficulty":"easy"},
    {"q":"Which country hosts the city of Tokyo?","options":["China","South Korea","Japan","Thailand"],"answer":2,"category":"Geography","difficulty":"easy"},
    {"q":"What is 7 x 8?","options":["54","56","58","48"],"answer":1,"category":"Math","difficulty":"easy"},
    {"q":"Which instrument has keys, pedals and strings?","options":["Guitar","Piano","Violin","Flute"],"answer":1,"category":"Music","difficulty":"easy"},
    {"q":"Who is known as the Father of Computers?","options":["Alan Turing","Charles Babbage","Bill Gates","Steve Jobs"],"answer":1,"category":"Technology","difficulty":"medium"},
    {"q":"Which ocean is the largest?","options":["Atlantic","Indian","Pacific","Arctic"],"answer":2,"category":"Geography","difficulty":"easy"},
    {"q":"What is the chemical symbol for Gold?","options":["Au","Ag","Gd","Go"],"answer":0,"category":"Chemistry","difficulty":"medium"},
    {"q":"Which planet has a prominent ring system?","options":["Earth","Mars","Saturn","Mercury"],"answer":2,"category":"Space","difficulty":"easy"},
    {"q":"Which language is primarily used for Android app development?","options":["Swift","Kotlin","Ruby","PHP"],"answer":1,"category":"Technology","difficulty":"medium"},
    {"q":"Who painted The Starry Night?","options":["Van Gogh","Monet","Dali","Kandinsky"],"answer":0,"category":"Art","difficulty":"medium"},
    {"q":"What is the capital city of Australia?","options":["Sydney","Melbourne","Canberra","Brisbane"],"answer":2,"category":"Geography","difficulty":"medium"},
    {"q":"What does HTTP stand for?","options":["HyperText Transfer Protocol","HighText Transfer Protocol","HyperText Transmission Protocol","Hyperlink Transfer Protocol"],"answer":0,"category":"Technology","difficulty":"medium"},
    {"q":"Which number is known as 'dozen'?","options":["10","12","15","20"],"answer":1,"category":"Math","difficulty":"easy"},
    {"q":"Who discovered penicillin?","options":["Alexander Fleming","Marie Curie","Louis Pasteur","Gregor Mendel"],"answer":0,"category":"Science","difficulty":"medium"},
    {"q":"Which city is known as the Big Apple?","options":["Los Angeles","Chicago","New York","Seattle"],"answer":2,"category":"Culture","difficulty":"easy"},
    {"q":"Which animal is the symbol of the WWF?","options":["Tiger","Panda","Elephant","Kangaroo"],"answer":1,"category":"Nature","difficulty":"easy"},
    {"q":"What is 100 in Roman numerals?","options":["L","C","D","M"],"answer":1,"category":"History","difficulty":"easy"},
    {"q":"Which element is needed for respiration?","options":["Nitrogen","Oxygen","Carbon","Sulfur"],"answer":1,"category":"Biology","difficulty":"easy"},
    {"q":"How many continents are there?","options":["5","6","7","8"],"answer":2,"category":"Geography","difficulty":"easy"},
    {"q":"Who wrote 'The Odyssey'?","options":["Homer","Socrates","Plato","Aristotle"],"answer":0,"category":"Literature","difficulty":"medium"},
    {"q":"Which is the fastest land animal?","options":["Lion","Cheetah","Horse","Gazelle"],"answer":1,"category":"Nature","difficulty":"easy"},
    {"q":"Which metal is liquid at room temperature?","options":["Mercury","Iron","Gold","Silver"],"answer":0,"category":"Chemistry","difficulty":"medium"},
    {"q":"Which programming language is known for data analysis?","options":["Python","HTML","CSS","Bash"],"answer":0,"category":"Technology","difficulty":"easy"},
    {"q":"What is the largest planet in our solar system?","options":["Earth","Jupiter","Saturn","Neptune"],"answer":1,"category":"Space","difficulty":"easy"},
    {"q":"Which sea creature has eight legs?","options":["Starfish","Octopus","Shark","Dolphin"],"answer":1,"category":"Nature","difficulty":"easy"},
    {"q":"Who is the author of 'Harry Potter'?","options":["J.R.R. Tolkien","J.K. Rowling","C.S. Lewis","Roald Dahl"],"answer":1,"category":"Literature","difficulty":"easy"},
    {"q":"Which country gifted the Statue of Liberty to the USA?","options":["England","France","Spain","Germany"],"answer":1,"category":"History","difficulty":"medium"},
    {"q":"What is the main gas in Earth's atmosphere?","options":["Oxygen","Carbon Dioxide","Nitrogen","Hydrogen"],"answer":2,"category":"Science","difficulty":"easy"},
    {"q":"Which organ pumps blood through the body?","options":["Lungs","Liver","Heart","Kidney"],"answer":2,"category":"Biology","difficulty":"easy"},
    {"q":"What language is primarily spoken in Brazil?","options":["Spanish","Portuguese","English","French"],"answer":1,"category":"Culture","difficulty":"easy"},
    {"q":"Which instrument is used to measure temperature?","options":["Barometer","Thermometer","Ammeter","Hygrometer"],"answer":1,"category":"Science","difficulty":"easy"},
    {"q":"What does 'GPS' stand for?","options":["Global Positioning System","General Positioning Service","Global Position System","Geographic Position Service"],"answer":0,"category":"Technology","difficulty":"medium"},
    {"q":"What is 9 squared?","options":["81","72","99","108"],"answer":0,"category":"Math","difficulty":"easy"},
    {"q":"Which vitamin is produced when skin is exposed to sunlight?","options":["Vitamin A","Vitamin C","Vitamin D","Vitamin K"],"answer":2,"category":"Health","difficulty":"medium"},
    {"q":"Which city hosted the 2016 Summer Olympics?","options":["Beijing","London","Rio de Janeiro","Tokyo"],"answer":2,"category":"Sports","difficulty":"medium"},
    {"q":"Who invented the telephone?","options":["Alexander Graham Bell","Thomas Edison","Nikola Tesla","Guglielmo Marconi"],"answer":0,"category":"History","difficulty":"medium"},
    {"q":"Which continent is Egypt located in?","options":["Asia","Africa","Europe","South America"],"answer":1,"category":"Geography","difficulty":"easy"},
    {"q":"What is the freezing point of water in Celsius?","options":["0","32","100","-1"],"answer":0,"category":"Science","difficulty":"easy"},
    {"q":"Which element's chemical symbol is 'Na'?","options":["Nitrogen","Sodium","Neon","Nickel"],"answer":1,"category":"Chemistry","difficulty":"medium"},
    {"q":"Who painted The Last Supper?","options":["Leonardo da Vinci","Van Gogh","Rembrandt","Picasso"],"answer":0,"category":"Art","difficulty":"medium"},
    {"q":"What is the capital of Canada?","options":["Toronto","Vancouver","Ottawa","Montreal"],"answer":2,"category":"Geography","difficulty":"medium"},
    {"q":"Which planet is closest to the Sun?","options":["Venus","Mercury","Mars","Earth"],"answer":1,"category":"Space","difficulty":"easy"},
    {"q":"Who wrote 'Pride and Prejudice'?","options":["Emily Bronte","Jane Austen","Charlotte Bronte","George Eliot"],"answer":1,"category":"Literature","difficulty":"medium"},
    {"q":"Which gas is essential for combustion?","options":["Carbon Dioxide","Oxygen","Nitrogen","Helium"],"answer":1,"category":"Science","difficulty":"easy"},
    {"q":"What is 15% of 200?","options":["20","25","30","35"],"answer":2,"category":"Math","difficulty":"easy"},
    {"q":"Which sport uses a shuttlecock?","options":["Tennis","Badminton","Squash","Table Tennis"],"answer":1,"category":"Sports","difficulty":"easy"},
    {"q":"Which country is known for the maple leaf symbol?","options":["USA","Canada","UK","Australia"],"answer":1,"category":"Culture","difficulty":"easy"},
    {"q":"Which famous scientist proposed laws of motion?","options":["Kepler","Galileo","Newton","Einstein"],"answer":2,"category":"Science","difficulty":"medium"},
    {"q":"Which city is famous for the Eiffel Tower?","options":["Rome","Paris","Berlin","Madrid"],"answer":1,"category":"Geography","difficulty":"easy"},
    {"q":"Which organelle is known as the powerhouse of the cell?","options":["Nucleus","Mitochondria","Ribosome","Chloroplast"],"answer":1,"category":"Biology","difficulty":"medium"},
    {"q":"What is the chemical formula for table salt?","options":["KCl","NaCl","H2O","CO2"],"answer":1,"category":"Chemistry","difficulty":"easy"},
    {"q":"Which author created Sherlock Holmes?","options":["Agatha Christie","Arthur Conan Doyle","Edgar Allan Poe","Ian Fleming"],"answer":1,"category":"Literature","difficulty":"medium"},
    {"q":"Which continent is Argentina in?","options":["Asia","Africa","South America","Europe"],"answer":2,"category":"Geography","difficulty":"easy"},
    {"q":"What is the value of Pi (approx)?","options":["2.14","3.14","4.13","3.41"],"answer":1,"category":"Math","difficulty":"easy"},
    {"q":"Which device is used to look at distant objects in space?","options":["Microscope","Telescope","Periscope","Spectrometer"],"answer":1,"category":"Science","difficulty":"easy"},
    {"q":"Which composer wrote the Four Seasons?","options":["Bach","Vivaldi","Mozart","Beethoven"],"answer":1,"category":"Music","difficulty":"medium"},
    {"q":"What is the largest organ in the human body?","options":["Liver","Brain","Skin","Heart"],"answer":2,"category":"Biology","difficulty":"medium"},
    {"q":"Which is the smallest continent by area?","options":["Europe","Antarctica","Australia","South America"],"answer":2,"category":"Geography","difficulty":"medium"},
    {"q":"Who discovered gravity when an apple fell?","options":["Galileo","Newton","Einstein","Pascal"],"answer":1,"category":"Science","difficulty":"easy"},
    {"q":"What is the boiling point of water at sea level (°C)?","options":["90","95","100","110"],"answer":2,"category":"Science","difficulty":"easy"},
    {"q":"Which language is primarily spoken in Argentina?","options":["Portuguese","Spanish","English","French"],"answer":1,"category":"Culture","difficulty":"easy"},
    {"q":"Which mammal lays eggs?","options":["Kangaroo","Platypus","Whale","Dog"],"answer":1,"category":"Nature","difficulty":"medium"},
    {"q":"Which chemical element has atomic number 1?","options":["Hydrogen","Helium","Lithium","Oxygen"],"answer":0,"category":"Chemistry","difficulty":"easy"},
    {"q":"Which city is the capital of Italy?","options":["Milan","Naples","Rome","Venice"],"answer":2,"category":"Geography","difficulty":"easy"},
    {"q":"Which sport is known as the 'king of sports'?","options":["Cricket","Basketball","Football (Soccer)","Tennis"],"answer":2,"category":"Sports","difficulty":"easy"},
    {"q":"Which metal is used to make electric wires due to high conductivity?","options":["Iron","Copper","Aluminum","Gold"],"answer":1,"category":"Technology","difficulty":"medium"},
    {"q":"Who is the author of 'The Iliad'?","options":["Homer","Sophocles","Euripides","Herodotus"],"answer":0,"category":"Literature","difficulty":"medium"},
    {"q":"Which programming language is often used for web front-end?","options":["Python","JavaScript","C++","Go"],"answer":1,"category":"Technology","difficulty":"easy"},
    {"q":"Which gas do humans exhale?","options":["Oxygen","Carbon Dioxide","Nitrogen","Hydrogen"],"answer":1,"category":"Biology","difficulty":"easy"},
    {"q":"What is the currency of Japan?","options":["Yen","Dollar","Euro","Won"],"answer":0,"category":"Economy","difficulty":"easy"},
    {"q":"Which is the tallest mountain in the world?","options":["K2","Kangchenjunga","Mount Everest","Lhotse"],"answer":2,"category":"Nature","difficulty":"medium"},
    {"q":"Which scientist is famous for the equation E=mc^2?","options":["Newton","Bohr","Einstein","Fermi"],"answer":2,"category":"Science","difficulty":"medium"},
    {"q":"Which fruit is a cross between kiwi and strawberry?","options":["Pineberry","Kumquat","Tamarillo","Guava"],"answer":0,"category":"Food","difficulty":"hard"},
    {"q":"Which country is called the Land of the Rising Sun?","options":["China","Japan","Thailand","India"],"answer":1,"category":"Culture","difficulty":"easy"},
    {"q":"What is 11 x 11?","options":["121","111","132","101"],"answer":0,"category":"Math","difficulty":"easy"},
    {"q":"Which is the largest desert in the world?","options":["Sahara","Gobi","Antarctic Desert","Kalahari"],"answer":2,"category":"Geography","difficulty":"medium"},
    {"q":"Who painted Girl with a Pearl Earring?","options":["Vermeer","Rembrandt","Goya","Rubens"],"answer":0,"category":"Art","difficulty":"medium"},
    {"q":"Which blood type is known as universal donor?","options":["A","B","AB","O"],"answer":3,"category":"Health","difficulty":"medium"},
    {"q":"Which ocean borders the east coast of the United States?","options":["Pacific","Atlantic","Indian","Arctic"],"answer":1,"category":"Geography","difficulty":"easy"},
    {"q":"What does DNA stand for?","options":["Deoxyribonucleic acid","Ribonucleic acid","Deoxyribose nucleic acid","None of these"],"answer":0,"category":"Biology","difficulty":"medium"},
    {"q":"Which is the longest river in the world?","options":["Nile","Amazon","Yangtze","Mississippi"],"answer":0,"category":"Geography","difficulty":"medium"},
    {"q":"Which instrument measures atmospheric pressure?","options":["Thermometer","Barometer","Hygrometer","Altimeter"],"answer":1,"category":"Science","difficulty":"medium"},
    {"q":"Who is known for the theory of evolution by natural selection?","options":["Darwin","Lamarck","Mendel","Watson"],"answer":0,"category":"Science","difficulty":"medium"},
    {"q":"Which company created the iPhone?","options":["Samsung","Apple","Nokia","Motorola"],"answer":1,"category":"Technology","difficulty":"easy"},
    {"q":"What is the process by which plants make food?","options":["Respiration","Photosynthesis","Transpiration","Digestion"],"answer":1,"category":"Biology","difficulty":"easy"},
    {"q":"Which city is known as the City of Love?","options":["Venice","Paris","Rome","Barcelona"],"answer":1,"category":"Culture","difficulty":"easy"},
    {"q":"Which molecule carries genetic instructions?","options":["RNA","DNA","Protein","Lipid"],"answer":1,"category":"Biology","difficulty":"medium"},
    {"q":"What is the next prime after 7?","options":["9","10","11","13"],"answer":2,"category":"Math","difficulty":"easy"},
    {"q":"Which fictional detective lived at 221B Baker Street?","options":["Hercule Poirot","Sherlock Holmes","Sam Spade","Philip Marlowe"],"answer":1,"category":"Literature","difficulty":"medium"},
    {"q":"Which planet is known for its Great Red Spot?","options":["Mars","Jupiter","Saturn","Neptune"],"answer":1,"category":"Space","difficulty":"medium"},
    {"q":"Who wrote 'The Divine Comedy'?","options":["Dante Alighieri","Geoffrey Chaucer","John Milton","Homer"],"answer":0,"category":"Literature","difficulty":"hard"},
    {"q":"Which metal has the highest electrical conductivity?","options":["Silver","Copper","Gold","Aluminum"],"answer":0,"category":"Chemistry","difficulty":"hard"},
    {"q":"What is the primary language spoken in Egypt?","options":["Arabic","English","French","Spanish"],"answer":0,"category":"Culture","difficulty":"easy"},
    {"q":"Which organ filters blood in the human body?","options":["Liver","Kidney","Spleen","Pancreas"],"answer":1,"category":"Biology","difficulty":"medium"},
    {"q":"Which country is the largest by area?","options":["USA","Canada","Russia","China"],"answer":2,"category":"Geography","difficulty":"medium"},
    {"q":"Which artist painted The Persistence of Memory?","options":["Dali","Picasso","Matisse","Klee"],"answer":0,"category":"Art","difficulty":"hard"},
    {"q":"Which system controls hormones in the body?","options":["Nervous system","Endocrine system","Digestive system","Respiratory system"],"answer":1,"category":"Biology","difficulty":"medium"},
    {"q":"What is the capital of India?","options":["Mumbai","New Delhi","Kolkata","Chennai"],"answer":1,"category":"Geography","difficulty":"easy"},
    {"q":"Which programming paradigm emphasizes objects?","options":["Functional","Procedural","Object-Oriented","Logic"],"answer":2,"category":"Technology","difficulty":"medium"},
    {"q":"Which gas makes up most of Earth's atmosphere?","options":["Oxygen","Carbon Dioxide","Nitrogen","Argon"],"answer":2,"category":"Science","difficulty":"easy"},
    {"q":"Which chess piece moves in an L-shape?","options":["Bishop","Knight","Rook","Queen"],"answer":1,"category":"Games","difficulty":"easy"},
    {"q":"Which country hosted the 2008 Olympics?","options":["Greece","China","UK","USA"],"answer":1,"category":"Sports","difficulty":"medium"},
    {"q":"Which organ produces insulin?","options":["Liver","Pancreas","Thyroid","Adrenal gland"],"answer":1,"category":"Health","difficulty":"medium"},
    {"q":"What is the value of 2^10?","options":["1024","1000","512","2048"],"answer":0,"category":"Math","difficulty":"medium"},
    {"q":"Which planet is known as an ice giant?","options":["Venus","Uranus","Mercury","Mars"],"answer":1,"category":"Space","difficulty":"hard"},
    {"q":"Who is the author of '1984'?","options":["Aldous Huxley","George Orwell","Ray Bradbury","Kurt Vonnegut"],"answer":1,"category":"Literature","difficulty":"medium"},
    {"q":"Which element is most abundant in the Earth's crust?","options":["Oxygen","Silicon","Aluminum","Iron"],"answer":0,"category":"Chemistry","difficulty":"hard"},
    {"q":"What is the study of the mind called?","options":["Biology","Sociology","Psychology","Anthropology"],"answer":2,"category":"Social","difficulty":"medium"},
    {"q":"Which country uses the rupee as currency?","options":["Japan","India","USA","UK"],"answer":1,"category":"Economy","difficulty":"easy"},
    {"q":"Which musical clef is used for higher pitches?","options":["Bass clef","Treble clef","Alto clef","Tenor clef"],"answer":1,"category":"Music","difficulty":"medium"},
    {"q":"Which element has the symbol 'K'?","options":["Potassium","Krypton","Calcium","Phosphorus"],"answer":0,"category":"Chemistry","difficulty":"easy"},
    {"q":"Which is the largest artery in the human body?","options":["Pulmonary artery","Aorta","Carotid artery","Femoral artery"],"answer":1,"category":"Biology","difficulty":"hard"},
    {"q":"Which bird is known for mimicking human speech?","options":["Sparrow","Crow","Parrot","Eagle"],"answer":2,"category":"Nature","difficulty":"easy"},
    {"q":"Which language is used to style web pages?","options":["HTML","Python","CSS","SQL"],"answer":2,"category":"Technology","difficulty":"easy"},
    {"q":"What is the powerhouse of the cell?","options":["Nucleus","Mitochondria","Ribosome","Golgi apparatus"],"answer":1,"category":"Biology","difficulty":"easy"},
    {"q":"Which painter is associated with Cubism?","options":["Picasso","Van Gogh","Rembrandt","Monet"],"answer":0,"category":"Art","difficulty":"hard"},
    {"q":"Which year did the Titanic sink?","options":["1910","1912","1914","1920"],"answer":1,"category":"History","difficulty":"medium"},
    {"q":"Which famous scientist worked at the patent office in Bern?","options":["Max Planck","Albert Einstein","Niels Bohr","Erwin Schrodinger"],"answer":1,"category":"Science","difficulty":"hard"},
    {"q":"Which city is known as the Silicon Valley?","options":["San Francisco","Palo Alto","Mountain View","Santa Clara"],"answer":1,"category":"Technology","difficulty":"medium"},
    {"q":"Which planet has the most moons?","options":["Earth","Mars","Jupiter","Venus"],"answer":2,"category":"Space","difficulty":"medium"},
    {"q":"Which is the longest bone in the human body?","options":["Femur","Tibia","Humerus","Fibula"],"answer":0,"category":"Biology","difficulty":"medium"},
    {"q":"Which country hosted the first modern Olympics in 1896?","options":["France","Greece","UK","USA"],"answer":1,"category":"History","difficulty":"hard"},
    {"q":"Which ocean lies between Africa and Australia?","options":["Atlantic","Indian","Pacific","Southern"],"answer":1,"category":"Geography","difficulty":"medium"},
    {"q":"Which gas is used to fill balloons to make them float?","options":["Oxygen","Helium","Nitrogen","Carbon Dioxide"],"answer":1,"category":"Science","difficulty":"easy"},
    {"q":"Which famous playwright wrote Hamlet?","options":["Shakespeare","Moliere","Ibsen","Chekhov"],"answer":0,"category":"Literature","difficulty":"easy"},
    {"q":"What is the main language spoken in Quebec (Canada)?","options":["English","French","Spanish","German"],"answer":1,"category":"Culture","difficulty":"easy"},
    {"q":"Which instrument has six strings typically?","options":["Violin","Cello","Guitar","Harp"],"answer":2,"category":"Music","difficulty":"easy"},
    {"q":"Which is the capital of Russia?","options":["Moscow","Saint Petersburg","Kazan","Sochi"],"answer":0,"category":"Geography","difficulty":"easy"},
    {"q":"Which planet is nicknamed Earth's twin?","options":["Mars","Venus","Mercury","Neptune"],"answer":1,"category":"Space","difficulty":"medium"},
    {"q":"Which scientist is associated with radioactivity discovery?","options":["Marie Curie","Rosalind Franklin","Jane Goodall","Barbara McClintock"],"answer":0,"category":"Science","difficulty":"hard"},
    {"q":"What is the capital of Egypt?","options":["Cairo","Alexandria","Giza","Luxor"],"answer":0,"category":"Geography","difficulty":"easy"},
    {"q":"Which is the heaviest naturally occurring element?","options":["Lead","Uranium","Plutonium","Osmium"],"answer":1,"category":"Chemistry","difficulty":"hard"}
]
# ---------------- End question bank ----------------

# ---------- Utility functions ----------

def upsert_user(user_id: int, username: Optional[str]):
    users.update_one({"user_id": user_id}, {"$set": {"username": username, "last_seen": datetime.utcnow()},
                    "$setOnInsert": {"points": 0, "correct": 0, "wrong": 0, "streak": 0, "best_streak": 0}}, upsert=True)


def seed_embedded_questions():
    inserted = 0
    for q in QUESTIONS:
        if not questions.find_one({"q": q["q"]}):
            questions.insert_one(q)
            inserted += 1
    return inserted


def create_group_session(chat_id: int, category: Optional[str] = None) -> Dict[str, Any]:
    session_id = f"group_{chat_id}"
    sess = {"session_id": session_id, "chat_id": chat_id, "category": category, "active": True, "current_q": None, "last_posted_at": None, "question_number": 0, "cooldown_until": None}
    sessions.update_one({"session_id": session_id}, {"$set": sess}, upsert=True)
    return sess


def end_group_session(chat_id: int):
    session_id = f"group_{chat_id}"
    sessions.update_one({"session_id": session_id}, {"$set": {"active": False}})


def get_group_session(chat_id: int) -> Optional[Dict[str, Any]]:
    return sessions.find_one({"session_id": f"group_{chat_id}"})


def pick_question(category: Optional[str] = None, difficulty: Optional[str] = None) -> Optional[Dict[str, Any]]:
    match = {}
    if category: match["category"] = category
    if difficulty: match["difficulty"] = difficulty
    q = list(questions.aggregate([{"$match": match}, {"$sample": {"size": 1}}]))
    return q[0] if q else None


def make_options_keyboard(session_id: str, options: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        rows.append([InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"answer|{session_id}|{i}")])
    rows.append([InlineKeyboardButton("Skip", callback_data=f"skip|{session_id}"), InlineKeyboardButton("Stop Quiz", callback_data=f"stop|{session_id}")])
    return InlineKeyboardMarkup(rows)


def record_group_score(chat_id: int, user_id: int, username: str, points: int):
    group_scores.update_one({"chat_id": chat_id, "user_id": user_id}, {"$inc": {"points": points}, "$set": {"username": username}}, upsert=True)
    users.update_one({"user_id": user_id}, {"$inc": {"points": points}}, upsert=True)

# ---------- Bot app ----------
app = Client("adv_quiz_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------- Commands ----------
@app.on_message(filters.group & filters.command("gquiz"))
async def cmhd_quiz(client: Client, message: Message):
    chat_id = message.chat.id
    upsert_user(message.from_user.id, message.from_user.username)
    sess = get_group_session(chat_id)
    if sess and sess.get("active"):
        await message.reply_text("A quiz is already active in this group. Use /stopquiz to stop it.")
        return
    create_group_session(chat_id)
    await message.reply_text("Quiz started! First correct answer gets points. Use /gleaderboard for group rankings.")
    await asyncio.sleep(1)
    await post_next_question(chat_id, client)


@app.on_message(filters.group & filters.command("stopquiz"))
async def cmd_stop_quiz(client: Client, message: Message):
    chat_id = message.chat.id
    sess = get_group_session(chat_id)
    if not sess or not sess.get("active"):
        await message.reply_text("No active quiz in this group.")
        return
    end_group_session(chat_id)
    await message.reply_text("Quiz stopped.")


@app.on_message(filters.group & filters.command("gleaderboard"))
async def cmd_gleaderboard(client: Client, message: Message):
    chat_id = message.chat.id
    top = list(group_scores.find({"chat_id": chat_id}).sort("points", DESCENDING).limit(10))
    if not top:
        await message.reply_text("No scores yet in this group.")
        return
    txt = "🏆 Group leaderboard:\n"
    for i, row in enumerate(top, start=1):
        txt += f"{i}. {row.get('username','unknown')} — {row.get('points',0)} pts\n"
    await message.reply_text(txt)


@app.on_message(filters.private & filters.command("global_leaderboard"))
async def cmd_global_leaderboard(client: Client, message: Message):
    top = list(users.find().sort("points", DESCENDING).limit(10))
    if not top:
        await message.reply_text("No global scores yet.")
        return
    txt = "🏆 Global leaderboard:\n"
    for i, u in enumerate(top, start=1):
        txt += f"{i}. @{u.get('username','unknown')} — {u.get('points',0)} pts\n"
    await message.reply_text(txt)


@app.on_message(filters.command("gprofile"))
async def cmd_grrprofile(client: Client, message: Message):
    uid = message.from_user.id
    doc = users.find_one({"user_id": uid}) or {}
    txt = (f"Profile — @{doc.get('username', message.from_user.username)}\n"
           f"Points: {doc.get('points',0)}\n"
           f"Correct: {doc.get('correct',0)}  Wrong: {doc.get('wrong',0)}\n"
           f"Best streak: {doc.get('best_streak',0)}")
    await message.reply_text(txt)


@app.on_message(filters.command("gaddq"))
async def cmd_gaddq(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply_text("Only admins can add questions.")
        return
    try:
        payload = message.text.split(" ", 1)[1]
        data = json.loads(payload)
        opts = data.get("options", [])
        if not (2 <= len(opts) <= MAX_OPTIONS):
            await message.reply_text(f"Options must be 2..{MAX_OPTIONS} items")
            return
        qdoc = {"q": data["q"], "options": opts, "answer": int(data["answer"]), "category": data.get("category","General"), "difficulty": data.get("difficulty","easy")}
        questions.insert_one(qdoc)
        await message.reply_text("Question added.")
    except Exception as e:
        await message.reply_text(f"Usage: /addq {json.dumps({'q':'Q','options':['a','b'],'answer':0})}\nError: {e}")


@app.on_message(filters.command("gseed"))
async def cmd_segged(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply_text("Only admins can seed.")
        return
    n = seed_embedded_questions()
    await message.reply_text(f"Seeded {n} embedded questions.")


@app.on_message(filters.command("gimport"))
async def cmd_import(client: Client, message: Message):
    # /import <json-array>
    if message.from_user.id not in ADMIN_IDS:
        await message.reply_text("Only admins can import questions.")
        return
    try:
        payload = message.text.split(" ",1)[1]
        arr = json.loads(payload)
        inserted = 0
        for q in arr:
            if not questions.find_one({"q": q.get("q")}):
                questions.insert_one(q)
                inserted += 1
        await message.reply_text(f"Imported {inserted} questions.")
    except Exception as e:
        await message.reply_text(f"Import failed: {e}")

# ------------ Core: posting & timeout ------------

async def post_next_question(chat_id: int, client: Client):
    sess = get_group_session(chat_id)
    if not sess or not sess.get("active"):
        return
    # cooldown check
    now = datetime.utcnow()
    if sess.get("cooldown_until") and sess["cooldown_until"] > now:
        return
    qdoc = pick_question(sess.get("category"))
    if not qdoc:
        await client.send_message(chat_id, "No questions available. Admins: add questions with /addq or /import or /seed.")
        return
    payload = {"q_id": str(qdoc.get("_id")), "q": qdoc["q"], "options": qdoc["options"], "answer": int(qdoc["answer"]), "posted_at": datetime.utcnow(), "deadline": datetime.utcnow() + timedelta(seconds=QUESTION_TIMEOUT)}
    sessions.update_one({"session_id": sess["session_id"]}, {"$set": {"current_q": payload, "last_posted_at": datetime.utcnow(), "question_number": sess.get("question_number",0)+1, "cooldown_until": datetime.utcnow() + timedelta(seconds=SESSION_COOLDOWN)}})
    kb = make_options_keyboard(sess["session_id"], payload["options"])
    text = f"Q{sess.get('question_number',0)+1}: {payload['q']}\n(First correct gets base points)"
    await client.send_message(chat_id, text, reply_markup=kb)

    # schedule timeout
    async def timeout_handler():
        await asyncio.sleep(QUESTION_TIMEOUT)
        s = get_group_session(chat_id)
        if not s or not s.get("active"): return
        cur = s.get("current_q")
        if cur and not cur.get("answered_by"):
            ans = cur.get("answer")
            letter = chr(65 + ans)
            await client.send_message(chat_id, f"⏰ Time's up! Correct answer: {letter}")
            await asyncio.sleep(1)
            await post_next_question(chat_id, client)
    asyncio.create_task(timeout_handler())

# ---------- Callback handlers ----------

@app.on_callback_query(filters.regex(r"^answer\|group_"))
async def cb_answer_group(client: Client, cq: CallbackQuery):
    parts = cq.data.split("|")
    if len(parts) < 3:
        await cq.answer('Bad data', show_alert=True); return
    _, session_id, idx_s = parts
    try:
        idx = int(idx_s)
    except:
        await cq.answer('Bad index', show_alert=True); return
    s = sessions.find_one({"session_id": session_id, "active": True})
    if not s:
        await cq.answer('No active quiz', show_alert=True); return
    cur = s.get("current_q")
    if not cur:
        await cq.answer('No active question', show_alert=True); return
    chat_id = s["chat_id"]
    if cur.get("answered_by"):
        await cq.answer('Already answered', show_alert=True); return
    if datetime.utcnow() > cur.get("deadline"):
        await cq.answer('Too late', show_alert=True); return
    user = cq.from_user
    # correctness
    if idx == cur.get("answer"):
        # calculate points with difficulty
        qdoc = questions.find_one({"_id": cur.get("q_id")}) if False else None
        # we didn't load difficulty; default medium
        base = POINTS_BASE.get('medium', 12)
        points = base
        record_group_score(chat_id, user.id, user.username or user.first_name, points)
        users.update_one({"user_id": user.id}, {"$inc": {"correct": 1, "points": points}, "$set": {"username": user.username}}, upsert=True)
        sessions.update_one({"session_id": session_id}, {"$set": {"current_q.answered_by": user.id, "current_q.answered_at": datetime.utcnow()}})
        await cq.message.reply_text(f"✅ {user.mention} answered correctly and earned {points} points!")
        await cq.answer('Correct')
        await asyncio.sleep(1.2)
        await post_next_question(chat_id, client)
    else:
        users.update_one({"user_id": user.id}, {"$inc": {"wrong": 1}}, upsert=True)
        await cq.answer('Wrong', show_alert=False)


@app.on_callback_query(filters.regex(r"^skip\|group_"))
async def cb_skip_group(client: Client, cq: CallbackQuery):
    _, session_id = cq.data.split("|")
    s = sessions.find_one({"session_id": session_id, "active": True})
    if not s:
        await cq.answer('No active quiz', show_alert=True); return
    sessions.update_one({"session_id": session_id}, {"$set": {"current_q.skipped": True}})
    await cq.message.reply_text("Question skipped. Posting next...")
    await cq.answer()
    await asyncio.sleep(0.8)
    await post_next_question(s["chat_id"], client)


@app.on_callback_query(filters.regex(r"^stop\|group_"))
async def cb_stop_group(client: Client, cq: CallbackQuery):
    _, session_id = cq.data.split("|")
    s = sessions.find_one({"session_id": session_id})
    if not s:
        await cq.answer('No session', show_alert=True); return
    end_group_session(s["chat_id"])
    await cq.message.reply_text("Quiz stopped by request.")
    await cq.answer()

# fallback
@app.on_callback_query(filters.regex(r"^answer\|"))
async def cb_answer_misc(client: Client, cq: CallbackQuery):
    await cq.answer()

