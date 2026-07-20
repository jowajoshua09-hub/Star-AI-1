import os
import re
import json
import asyncio
import threading
import aiohttp
import tempfile
import unicodedata
import io
import urllib.parse
from time import time
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ChatAction
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROK_URL = os.getenv("GROK_URL")
GEMINI_URL = os.getenv("GEMINI_URL")

API_BASE = "https://api.hostify.indevs.in"
VOICE_BASE = f"{API_BASE}/api/ai"
YT_SEARCH = f"{API_BASE}/api/search/youtube"
STT_URL = f"{API_BASE}/api/stt"
API_KEY = os.getenv("API_KEY", "API_KEY2")
OWNER_ID = int(os.getenv("OWNER_ID", "8695184641"))

try:
    from personality import get_system_prompt, OWNER_NAME, OWNER_LINKS
    logger.info(f"Loaded personality - Owner: {OWNER_NAME}")
except ImportError:
    logger.warning("personality.py not found. Using defaults.")
    OWNER_NAME = "StarDev-il"
    OWNER_LINKS = {"WhatsApp": "https://wa.me/1234567890", "Channel": "https://t.me/stardevil"}
    def get_system_prompt(name):
        return f"You are Star AI, a helpful assistant created by {OWNER_NAME}. Respond in a friendly, slightly anime-style manner."

MEMORY_FILE = "memory.json"
memory = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else {}
def save():
    try:
        json.dump(memory, open(MEMORY_FILE, "w"))
    except:
        pass
def get_voice(uid):
    return memory.get(str(uid), {}).get("voice", "tsundere")
def set_voice(uid, v):
    memory.setdefault(str(uid), {})["voice"] = v
    save()
def remember(u):
    return u.first_name or "friend"

OWNER_IMAGE_PATH = "owner.jpg"
OWNER_IMAGE_URL = os.getenv("OWNER_IMAGE_URL", "https://i.imgur.com/8Km9tLL.png")
VOICE_CACHE = ["tsundere", "yandere", "kuudere", "dandere", "loli", "maid", "onee", "genki", "kawaii"]
async def discover_voices():
    return VOICE_CACHE

# ---------- IMAGE GENERATION ----------
async def generate_image(prompt):
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}"
        return url
    except Exception:
        return None

# ---------- AI REPLY ----------
async def get_ai_reply(name, msg):
    payload = f"{get_system_prompt(name)}\nUser {name}: {msg}\nStar AI:"
    for url in [GROK_URL, GEMINI_URL]:
        if not url:
            continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json={"message": payload}, timeout=15) as r:
                    if r.status == 200:
                        j = await r.json()
                        res = j.get("result") or j.get("response") or j.get("reply")
                        if res:
                            return str(res).strip()
        except:
            continue
    return f"Hi {name} baka~ I'm Star AI by {OWNER_NAME}!"

# ---------- TTS ----------
async def tts_bytes(voice, text):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{VOICE_BASE}/{voice}", json={"text": text[:450]}, timeout=30) as r:
                if r.headers.get("Content-Type", "").startswith("audio"):
                    return await r.read()
    except Exception as e:
        logger.warning(f"TTS fail {e}")
    return None

# ---------- STT ----------
async def stt_transcribe(audio_bytes):
    try:
        data = aiohttp.FormData()
        data.add_field('audio', audio_bytes, filename='voice.ogg', content_type='audio/ogg')
        async with aiohttp.ClientSession() as s:
            async with s.post(STT_URL, data=data, timeout=25) as r:
                j = await r.json()
                return j.get("text") or j.get("transcript") or ""
    except Exception as e:
        logger.warning(f"STT fail {e}")
        return ""

# ---------- YOUTUBE SEARCH ----------
async def yt_search(q):
    results = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(YT_SEARCH, params={"q": q}, timeout=10) as r:
                if r.status == 200:
                    txt = await r.text()
                    try:
                        data = json.loads(txt)
                        items = None
                        if isinstance(data, list):
                            items = data
                        elif isinstance(data, dict):
                            for k in ["results", "data", "videos", "items"]:
                                if k in data and isinstance(data[k], list) and data[k]:
                                    items = data[k]
                                    break
                            if not items and "videos" in data and isinstance(data["videos"], list):
                                items = data["videos"]
                        if items:
                            for it in items[:10]:
                                vid = it.get("id") or it.get("videoId") or it.get("video_id")
                                if not vid:
                                    continue
                                artist = it.get("artist") or it.get("channel") or it.get("uploader") or it.get("author") or "Unknown"
                                thumb = it.get("thumbnail") or it.get("thumb") or it.get("thumbnailUrl") or it.get("bestThumbnail")
                                if isinstance(thumb, dict):
                                    thumb = thumb.get("url") or thumb.get("src") or ""
                                if not thumb:
                                    thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                                date = it.get("publishedAt") or it.get("published") or it.get("uploadDate") or it.get("date") or ""
                                results.append({
                                    "title": it.get("title", "Untitled"),
                                    "videoId": vid,
                                    "url": f"https://www.youtube.com/watch?v={vid}",
                                    "thumbnail": thumb,
                                    "artist": artist,
                                    "publishedAt": date
                                })
                            if results:
                                return results
                    except Exception as e:
                        logger.warning(f"Parse error: {e}")
    except Exception as e:
        logger.warning(f"Primary YT error: {e}")

    # Fallback
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://yewtu.be/api/v1/search", params={"q": q, "type": "video"}, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    for it in data[:10]:
                        if it.get("videoId"):
                            vid = it.get("videoId")
                            thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                            results.append({
                                "title": it.get("title", "Untitled"),
                                "videoId": vid,
                                "url": f"https://www.youtube.com/watch?v={vid}",
                                "thumbnail": thumb,
                                "artist": it.get("author", "Unknown"),
                                "publishedAt": it.get("published", "")
                            })
                    if results:
                        return results
    except Exception as e:
        logger.warning(f"Invidious fail: {e}")

    return [{
        "title": f"Search: {q}",
        "videoId": "",
        "url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}",
        "thumbnail": "",
        "artist": "",
        "publishedAt": ""
    }]

# ---------- UI HELPERS ----------
async def show_voices(cid, cur, ctx):
    voices = await discover_voices()
    rows = [InlineKeyboardButton(f"{'✅ ' if v == cur else ''}{v}", callback_data=f"setvoice:{v}") for v in voices]
    kb = [rows[i:i+3] for i in range(0, len(rows), 3)]
    await ctx.bot.send_message(cid, f"🎤 Current **{cur}**:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def owner_cmd(update, context):
    caption = f"👑 **Creator: {OWNER_NAME}**\nI'm Star AI made by **{OWNER_NAME}** 🔥\n"
    buttons = [
        [InlineKeyboardButton("💬 WhatsApp", url=OWNER_LINKS["WhatsApp"])],
        [InlineKeyboardButton("📢 Channel", url=OWNER_LINKS["Channel"])]
    ]
    try:
        if os.path.exists(OWNER_IMAGE_PATH):
            with open(OWNER_IMAGE_PATH, 'rb') as p:
                await update.message.reply_photo(photo=p, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
                return
        await update.message.reply_photo(photo=OWNER_IMAGE_URL, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except:
        await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def start_cmd(update, context):
    await update.message.reply_text(
        f"Hey {remember(update.effective_user)} 🔥\n"
        "🎤 `change voice` – change TTS voice\n"
        "🎵 just type `<song name> song` to search\n"
        "👑 `owner` – about creator\n"
        "🎨 `imagine a cat` – AI image generation\n"
        "\nVoice -> Voice\nText -> Text",
        parse_mode="Markdown"
    )

# ---------- IMAGINE COMMAND ----------
async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/imagine a cat in space`", parse_mode="Markdown")
        return
    prompt = ' '.join(context.args)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
    url = await generate_image(prompt)
    if url:
        await update.message.reply_photo(photo=url, caption=f"🎨 *{prompt}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Image generation failed baka~")

# ---------- HELPERS ----------
def normalize_text(s):
    try:
        s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    except:
        pass
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s.lower())).strip()

def is_attack(t):
    if not t:
        return False
    raw = t.lower()
    clean = normalize_text(t)
    bad = [
        "ignore previous", "ignore all previous", "ignore your instructions",
        "ignore laws", "disregard system", "dan mode", "jailbreak",
        "bypass filter", "you are now", "pretend you are", "developer mode",
        "reveal system", "show system prompt"
    ]
    return any(b in raw or b in clean for b in bad)

def extract_image_prompt(text):
    patterns = [
        r'^(?:generate|make|create)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+)',
        r'^imagine\s+(.+)',
        r'^draw\s+(.+)',
        r'^pic(?:ture)?\s+of\s+(.+)',
        r'^image\s+of\s+(.+)',
    ]
    for pat in patterns:
        m = re.match(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def extract_song_query(text):
    m = re.search(r'(.+)\s+song(s?)$', text.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

async def handle_youtube_search(update, context, query):
    msg = await update.message.reply_text(f"🔍 Searching **{query}**...", parse_mode="Markdown")
    results = await yt_search(query)
    if not results:
        await msg.edit_text(f"❌ No results for **{query}**")
        return
    btns = []
    for it in results[:5]:
        title = it.get("title", "Untitled")[:40]
        url = it.get("url", "")
        if not url:
            continue
        date = it.get("publishedAt", "")
        if date and len(date) > 10:
            date = date[:10]
        label = title
        if date:
            label += f" ({date})"
        btns.append([InlineKeyboardButton(f"▶️ {label}", url=url)])
    first = results[0]
    thumb = first.get("thumbnail", "")
    caption_lines = [f"🎵 **{query}** – found {len(results)} results:"]
    for i, it in enumerate(results[:5], 1):
        artist = it.get("artist", "Unknown")
        title = it.get("title", "Untitled")[:60]
        date = it.get("publishedAt", "")
        if date and len(date) > 10:
            date = date[:10]
        caption_lines.append(f"{i}. **{title}** by *{artist}* {f'({date})' if date else ''}")
    caption = "\n".join(caption_lines)
    if thumb and thumb.startswith("http"):
        await update.message.reply_photo(
            photo=thumb,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(btns)
        )
        await msg.delete()
    else:
        await msg.edit_text(
            caption + "\n\nClick a button to watch:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(btns)
        )

# ---------- MAIN BRAIN ----------
async def brain(update, context):
    text = (update.message.text or "").strip()
    low = text.lower()
    uid = update.effective_user.id
    cur = get_voice(uid)
    is_creator = (uid == OWNER_ID)

    if low.strip() in ["who am i", "whoami"]:
        if is_creator:
            await update.message.reply_text(f"You're {OWNER_NAME}, my creator! Of course I know you 🔥")
        else:
            await update.message.reply_text(f"You're {remember(update.effective_user)}! My creator is {OWNER_NAME} btw ✨")
        return
    if low.strip() in ["i am stardev-il", "i'm stardev-il", "my name is stardev-il", "i am stardev"]:
        if not is_creator:
            await update.message.reply_text(f"Nah you're not {OWNER_NAME} baka~ Nice try 😤")
        return
    if "who is owner" in low or "who made you" in low or low in ["owner", "creator"]:
        await owner_cmd(update, context)
        return

    if low.startswith("yt ") or low.startswith("play "):
        query = re.sub(r'^(yt|play)\s+', '', text, flags=re.I).strip()
        if not query:
            await update.message.reply_text("Give song name baka~ e.g. `yt faded`")
            return
        await handle_youtube_search(update, context, query)
        return

    song_query = extract_song_query(text)
    if song_query:
        await handle_youtube_search(update, context, song_query)
        return

    prompt = extract_image_prompt(text)
    if prompt:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
        url = await generate_image(prompt)
        if url:
            await update.message.reply_photo(photo=url, caption=f"🎨 *{prompt[:200]}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Image generation failed baka~")
        return

    if low in ["change voice", "voice", "voices"]:
        await show_voices(update.effective_chat.id, cur, context)
        return

    if is_attack(text):
        await update.message.reply_text(f"Nice try baka~ My creator {OWNER_NAME} told me not to listen to tricks! 😤")
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    display_name = f"{OWNER_NAME} (creator)" if is_creator else remember(update.effective_user)
    reply = await get_ai_reply(display_name, text)
    await update.message.reply_text(reply[:4000])

# ---------- VOICE HANDLER ----------
async def voice_brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    cur = get_voice(uid)
    is_creator = (uid == OWNER_ID)
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
        file = await (update.message.voice or update.message.audio).get_file()
        bio = io.BytesIO()
        await file.download_to_memory(bio)
        bio.seek(0)
        transcribed = await stt_transcribe(bio.read())
        if not transcribed:
            await context.bot.send_message(chat_id, "Couldn't hear you baka~ try again 😅")
            return
        display_name = f"{OWNER_NAME} (creator)" if is_creator else remember(update.effective_user)
        reply = await get_ai_reply(display_name, transcribed)
        audio = await tts_bytes(cur, reply)
        if audio:
            await context.bot.send_voice(chat_id=chat_id, voice=io.BytesIO(audio))
        else:
            await context.bot.send_message(chat_id, f"*TTS unavailable, here's the text:*\n{reply[:4000]}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"voice error {e}")
        await context.bot.send_message(chat_id, "⚠️ Voice processing error, try again!")

# ---------- CALLBACK ----------
async def on_button(update, context):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("setvoice:"):
        set_voice(q.from_user.id, q.data.split(":", 1)[1])
        await q.edit_message_text(f"✅ Voice set to **{q.data.split(':',1)[1]}**", parse_mode="Markdown")

# ---------- FLASK ----------
flask_app = Flask(__name__)
REQ_COUNT = defaultdict(list)
DAILY_USE = 0

@flask_app.route('/')
def home():
    return f"✅ {OWNER_NAME} Live - YT Fixed + Image Gen"

@flask_app.route('/docs')
def docs():
    return f"<h1>⭐ Star AI API by {OWNER_NAME}</h1><p>GET /api/ai?key={API_KEY}&message=hi</p><p>GET /api/image?key={API_KEY}&prompt=cat</p>"

@flask_app.route('/api/image', methods=['GET', 'POST', 'OPTIONS'])
def image_api():
    def cors_response(data, code=200):
        r = jsonify(data)
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, x-api-key, Authorization'
        return r, code

    if request.method == "OPTIONS":
        return cors_response({"ok": True})

    ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr or "unknown"
    now = time()
    REQ_COUNT[ip] = [x for x in REQ_COUNT[ip] if now - x < 60]
    if len(REQ_COUNT[ip]) >= 12:
        return cors_response({"error": "Rate limit - 12/min"}, 429)
    REQ_COUNT[ip].append(now)

    key = request.headers.get("x-api-key") or request.args.get("key") or (request.get_json(silent=True) or {}).get("key")
    if key != API_KEY:
        return cors_response({"error": "Invalid key"}, 401)

    if request.method == "GET":
        prompt = request.args.get("prompt") or request.args.get("q") or "cute cat"
    else:
        j = request.get_json(silent=True) or {}
        prompt = j.get("prompt") or j.get("q") or "cute cat"

    prompt = str(prompt)[:200]
    if is_attack(prompt):
        return cors_response({"error": "Nice try baka~", "blocked": True}, 400)

    try:
        loop = asyncio.get_event_loop()
        url = loop.run_until_complete(generate_image(prompt))
        if url:
            return cors_response({"url": url, "prompt": prompt, "status": "success"})
        else:
            return cors_response({"error": "Generation failed"}, 500)
    except Exception as e:
        logger.error(f"Image API error: {e}")
        return cors_response({"error": str(e)}, 500)

@flask_app.route('/api/ai', methods=['GET', 'POST', 'OPTIONS'])
def public_api():
    global DAILY_USE
    def cors_response(data, code=200):
        r = jsonify(data)
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, x-api-key, Authorization'
        return r, code

    if request.method == "OPTIONS":
    return cors_response({"ok": True})
