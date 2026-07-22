import os, re, json, asyncio, threading, aiohttp, tempfile, unicodedata, io, urllib.parse, random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ChatAction
from flask import Flask
import logging

from api_client import get_ai_reply
from personality import get_system_prompt, OWNER_NAME, OWNER_LINKS

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8695184641"))
PORT = int(os.getenv("PORT", 10000))

API_BASE = "https://api.hostify.indevs.in"
VOICE_BASE = f"{API_BASE}/api/ai"
YT_SEARCH = f"{API_BASE}/api/search/youtube"
STT_URL = os.getenv("STT_URL", f"{API_BASE}/api/stt")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------- Flask keep-alive ----------
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Star AI TG Bot Alive", 200
@flask_app.route('/health')
def health(): return "OK", 200
def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

# ---------- Config ----------
GROUP_USERNAME = "@startech372"
GROUP_ID = -1004383326043 # REPLACE THIS: Forward channel post to @userinfobot to get real ID
GROUP_LINK = "https://t.me/startech372"

WELCOME_TEXT = """Welcome to star AI ✨

🎤 `change voice` – change TTS
🎵 `yt song` – YouTube
👑 `owner`– creator
🎨 `imagine a cat` – AI image
Voice -> Voice
Text -> Text

Before use join channel below 👇"""

MEMORY_FILE = "memory.json"
memory = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else {}
def save():
    try: json.dump(memory, open(MEMORY_FILE, "w"))
    except: pass

def is_verified(uid): return memory.get(str(uid), {}).get("verified", False)
def set_verified(uid): memory.setdefault(str(uid), {})["verified"] = True; save()
def is_owner(uid): return uid == OWNER_ID
def get_voice(uid): return memory.get(str(uid), {}).get("voice", "tsundere")
def set_voice(uid, v): memory.setdefault(str(uid), {})["voice"] = v; save()
def remember(u): return u.first_name or "friend"

OWNER_IMAGE_PATH = "owner.jpg"
OWNER_IMAGE_URL = os.getenv("OWNER_IMAGE_URL", "https://i.imgur.com/8Km9tLL.png")
VOICE_CACHE = ["tsundere", "yandere", "kuudere", "dandere", "loli", "maid", "onee", "genki", "kawaii"]
async def discover_voices(): return VOICE_CACHE

async def is_user_in_channel(user_id, context):
    for chat in [GROUP_ID, GROUP_USERNAME]:
        try:
            m = await context.bot.get_chat_member(chat_id=chat, user_id=user_id)
            if m.status in ["member","administrator","creator","owner"]:
                return True
        except Exception as e:
            logger.warning(f"Check {chat} failed: {e}")
            continue
    return False

# ---------- Keyboards ----------
def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Join channel", url=GROUP_LINK)],
        [InlineKeyboardButton("Verify", callback_data="verify_group")]
    ])

# ---------- Image ----------
def get_image_url(prompt: str):
    prompt = prompt.strip()[:600]
    if not prompt: return None
    seed = random.randint(1, 9999999)
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true&enhance=true"

# ---------- All your other functions (yt, tts, stt, owner_cmd etc) KEEP SAME ----------
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
                        if isinstance(data, list): items = data
                        elif isinstance(data, dict):
                            for k in ["results", "data", "videos", "items"]:
                                if k in data and isinstance(data[k], list) and data[k]:
                                    items = data[k]; break
                        if items:
                            for it in items[:10]:
                                vid = it.get("id") or it.get("videoId") or it.get("video_id")
                                if not vid: continue
                                artist = it.get("artist") or it.get("channel") or "Unknown"
                                thumb = it.get("thumbnail") or f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                                if isinstance(thumb, dict): thumb = thumb.get("url") or ""
                                date = it.get("publishedAt") or ""
                                results.append({"title": it.get("title","Untitled"),"videoId":vid,"url":f"https://www.youtube.com/watch?v={vid}","thumbnail":thumb,"artist":artist,"publishedAt":date})
                            if results: return results
                    except: pass
    except: pass
    return results

async def tts_bytes(voice, text):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{VOICE_BASE}/{voice}", json={"text": text[:450]}, timeout=30) as r:
                if r.headers.get("Content-Type","").startswith("audio"): return await r.read()
    except: pass
    return None

async def stt_transcribe(audio_bytes):
    try:
        data = aiohttp.FormData()
        data.add_field('audio', audio_bytes, filename='voice.ogg', content_type='audio/ogg')
        async with aiohttp.ClientSession() as s:
            async with s.post(STT_URL, data=data, timeout=25) as r:
                if r.status==200:
                    j=await r.json(); return j.get("text") or j.get("transcript") or ""
    except: return ""
    return ""

async def show_voices(cid, cur, ctx):
    voices = await discover_voices()
    rows = [InlineKeyboardButton(f"{'✅ ' if v==cur else ''}{v}", callback_data=f"setvoice:{v}") for v in voices]
    kb = [rows[i:i+3] for i in range(0,len(rows),3)]
    await ctx.bot.send_message(cid, f"🎤 Current **{cur}**:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def owner_cmd(update, context):
    caption = f"👑 **Creator: {OWNER_NAME}**\nI'm Star AI made by **{OWNER_NAME}** 🔥\n"
    buttons = [[InlineKeyboardButton("💬 WhatsApp", url=OWNER_LINKS["WhatsApp"])],[InlineKeyboardButton("📢 Channel", url=OWNER_LINKS["Channel"])]]
    try:
        if os.path.exists(OWNER_IMAGE_PATH):
            with open(OWNER_IMAGE_PATH,'rb') as p:
                await update.message.reply_photo(photo=p, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)); return
        await update.message.reply_photo(photo=OWNER_IMAGE_URL, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    except:
        await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

# ---------- UNIFIED START & VERIFY ----------
async def start_cmd(update, context):
    uid = update.effective_user.id
    if is_owner(uid):
        set_verified(uid)
        await update.message.reply_text(f"{WELCOME_TEXT}\n\n✅ Creator mode!", parse_mode="Markdown", reply_markup=join_keyboard())
        return
    if is_verified(uid):
        if await is_user_in_channel(uid, context):
            await update.message.reply_text(f"{WELCOME_TEXT}\n\n✅ Already verified! Send anything.", parse_mode="Markdown")
            return
    # Not verified -> Same message as join first
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown", reply_markup=join_keyboard())

async def verification_required(update, context):
    # Now just calls same layout as start
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown", reply_markup=join_keyboard())

async def verify_user(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if is_owner(user_id):
        set_verified(user_id)
        await query.answer()
        await query.edit_message_text("✅ Creator verified! Enjoy! 🚀")
        return
    if await is_user_in_channel(user_id, context):
        set_verified(user_id)
        await query.answer("✅ Verified!")
        await query.edit_message_text(f"{WELCOME_TEXT}\n\n✅ **Verified! Now send any message 🚀**", parse_mode="Markdown")
    else:
        await query.answer("❌ You haven't joined yet. Join channel then press Verify.", show_alert=True)
        await query.edit_message_text(WELCOME_TEXT, parse_mode="Markdown", reply_markup=join_keyboard())

async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/imagine a cat in space`", parse_mode="Markdown"); return
    prompt = ' '.join(context.args)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
    url = get_image_url(prompt)
    if url:
        try: await update.message.reply_photo(photo=url, caption=f"🎨 *{prompt[:200]}*", parse_mode="Markdown")
        except: await update.message.reply_text(f"🎨 {prompt}\n{url}")

def normalize_text(s):
    try: s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode('ascii')
    except: pass
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 ]',' ',s.lower())).strip()
def is_attack(t):
    if not t: return False
    raw=t.lower(); clean=normalize_text(t)
    bad=["ignore previous","ignore all previous","ignore your instructions","dan mode","jailbreak"]
    return any(b in raw or b in clean for b in bad)
def extract_image_prompt(text):
    for pat in [r'^(?:generate|make|create)\s+(?:an?\s+)?image\s+(?:of\s+)?(.+)',r'^imagine\s+(.+)',r'^draw\s+(.+)']:
        m=re.match(pat,text,re.IGNORECASE)
        if m: return m.group(1).strip()
    return None
def extract_song_query(text):
    m=re.search(r'(.+)\s+song(s?)$',text.strip(),re.IGNORECASE)
    return m.group(1).strip() if m else None
async def handle_youtube_search(update, context, query):
    msg=await update.message.reply_text(f"🔍 Searching **{query}**...",parse_mode="Markdown")
    results=await yt_search(query)
    if not results: await msg.edit_text(f"❌ No results"); return
    btns=[[InlineKeyboardButton(f"▶️ {it.get('title','')[:40]}", url=it.get("url",""))] for it in results[:5] if it.get("url")]
    await msg.edit_text(f"🎵 **{query}** – {len(results)} results:",parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(btns))

async def brain(update, context):
    uid=update.effective_user.id
    if not is_verified(uid) and not is_owner(uid):
        await verification_required(update, context); return
    text=(update.message.text or "").strip(); low=text.lower()
    if "who is owner" in low or low in ["owner","creator"]: await owner_cmd(update, context); return
    if low.startswith("yt ") or low.startswith("play "):
        q=re.sub(r'^(yt|play)\s+','',text,flags=re.I).strip()
        await handle_youtube_search(update, context, q); return
    prompt=extract_image_prompt(text)
    if prompt:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
        url=get_image_url(prompt)
        try: await update.message.reply_photo(photo=url, caption=f"🎨 *{prompt[:200]}*", parse_mode="Markdown")
        except: await update.message.reply_text(f"{url}")
        return
    if low in ["change voice","voice","voices"]: await show_voices(update.effective_chat.id, get_voice(uid), context); return
    if is_attack(text): await update.message.reply_text(f"Nice try baka~ 😤"); return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    display_name=f"{OWNER_NAME} (creator)" if is_owner(uid) else remember(update.effective_user)
    reply=await get_ai_reply(str(uid), display_name, text)
    await update.message.reply_text(reply[:4000])

async def voice_brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if not is_verified(uid) and not is_owner(uid): await verification_required(update, context); return
    chat_id=update.effective_chat.id; cur=get_voice(uid)
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
        file=await (update.message.voice or update.message.audio).get_file()
        bio=io.BytesIO(); await file.download_to_memory(bio); bio.seek(0)
        transcribed=await stt_transcribe(bio.read())
        if not transcribed: await context.bot.send_message(chat_id,"Couldn't hear you 😅"); return
        reply=await get_ai_reply(str(uid), remember(update.effective_user), transcribed)
        audio=await tts_bytes(cur, reply)
        if audio: await context.bot.send_voice(chat_id=chat_id, voice=io.BytesIO(audio))
        else: await context.bot.send_message(chat_id, reply[:4000])
    except Exception as e:
        logger.error(f"voice error {e}")

async def on_button(update, context):
    q=update.callback_query; await q.answer()
    if q.data.startswith("setvoice:"): set_voice(q.from_user.id, q.data.split(":",1)[1]); await q.edit_message_text(f"✅ Voice set to **{q.data.split(':',1)[1]}**",parse_mode="Markdown")
    elif q.data=="verify_group": await verify_user(update, context)

async def main():
    if not TOKEN: print("❌ BOT_TOKEN missing"); return
    threading.Thread(target=run_flask, daemon=True).start()
    app=Application.builder().token(TOKEN).build()
    try: await app.bot.delete_webhook(drop_pending_updates=True)
    except: pass
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))
    app.add_handler(CommandHandler("imagine", imagine_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_brain))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, brain))
    await app.initialize(); await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    print(f"✅ Bot Live with unified /start + Join")
    await asyncio.Event().wait()

if __name__=="__main__":
    asyncio.run(main())