import os, re, json, asyncio, threading, aiohttp, tempfile, unicodedata, io, urllib.parse
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ChatAction
import logging

# ---------- Import from api_client ----------
from api_client import get_ai_reply, generate_image, flask_app

logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROK_URL = os.getenv("GROK_URL")
GEMINI_URL = os.getenv("GEMINI_URL")

API_BASE = "https://api.hostify.indevs.in"
VOICE_BASE = f"{API_BASE}/api/ai"
YT_SEARCH = f"{API_BASE}/api/search/youtube"
STT_URL = os.getenv("STT_URL", f"{API_BASE}/api/stt")
OWNER_ID = int(os.getenv("OWNER_ID", "8695184641"))

from personality import get_system_prompt, OWNER_NAME, OWNER_LINKS
print(f"✅ Loaded - Owner: {OWNER_NAME}")

MEMORY_FILE = "memory.json"
memory = json.load(open(MEMORY_FILE)) if os.path.exists(MEMORY_FILE) else {}
def save():
    try:
        json.dump(memory, open(MEMORY_FILE, "w"))
    except:
        pass

# ---------- Group Verification ----------
GROUP_USERNAME = "@startech372"
GROUP_LINK = "https://t.me/startech372"

def is_verified(uid):
    return memory.get(str(uid), {}).get("verified", False)

def set_verified(uid):
    memory.setdefault(str(uid), {})["verified"] = True
    save()

def is_owner(uid):
    return uid == OWNER_ID

# ---------- Voice & Memory ----------
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

# ---------- YouTube Search ----------
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
                    except:
                        pass
    except:
        pass

    # Fallback: Invidious
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
    except:
        pass

    return [{
        "title": f"Search: {q}",
        "videoId": "",
        "url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}",
        "thumbnail": "",
        "artist": "",
        "publishedAt": ""
    }]

# ---------- TTS & STT ----------
async def tts_bytes(voice, text):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{VOICE_BASE}/{voice}", json={"text": text[:450]}, timeout=30) as r:
                if r.headers.get("Content-Type", "").startswith("audio"):
                    return await r.read()
    except:
        pass
    return None

async def stt_transcribe(audio_bytes):
    try:
        data = aiohttp.FormData()
        data.add_field('audio', audio_bytes, filename='voice.ogg', content_type='audio/ogg')
        async with aiohttp.ClientSession() as s:
            async with s.post(STT_URL, data=data, timeout=25) as r:
                if r.status == 200:
                    j = await r.json()
                    return j.get("text") or j.get("transcript") or ""
                else:
                    return ""
    except:
        return ""

# ---------- UI Helpers ----------
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
        "🎵 `yt song` – search YouTube\n"
        "👑 `owner` – about creator\n"
        "🎨 `imagine a cat` – AI image generation\n"
        "\nVoice -> Voice\nText -> Text",
        parse_mode="Markdown"
    )

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

# ---------- Helpers ----------
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
    if not results or (len(results) == 1 and not results[0].get("videoId")):
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

# ---------- Verification Message ----------
async def verification_required(update, context):
    """Show verification message with group info and verify button."""
    text = (
        f"🌟 **Welcome to Star AI!**\n\n"
        f"Star AI is an intelligent, witty, and logical AI assistant created by {OWNER_NAME}.\n\n"
        f"**How it works:**\n"
        f"• 🎤 Send a voice note – I reply with voice\n"
        f"• 📝 Type a message – I chat with logic & memory\n"
        f"• 🎨 `imagine a cat` – generate AI images\n"
        f"• 🎵 `yt song` – search YouTube\n\n"
        f"**To use this bot, you MUST join our group first:**\n"
        f"Join 👉 {GROUP_LINK}\n\n"
        f"After joining, click **Verify ✅** below – I'll check instantly.\n"
        f"_(This check happens only once per user.)_"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Join Group", url=GROUP_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_group")]
    ]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def verify_user(update, context):
    """Handle the verify button callback."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # If owner, auto-verify
    if is_owner(user_id):
        set_verified(user_id)
        await query.edit_message_text("✅ You're the creator! Verified automatically. Now enjoy Star AI! 🚀")
        return

    # Check if user is in the group
    try:
        chat_member = await context.bot.get_chat_member(chat_id=GROUP_USERNAME, user_id=user_id)
        if chat_member.status in ["member", "administrator", "creator"]:
            set_verified(user_id)
            await query.edit_message_text("✅ **Verified!** You're a member of our group. Now enjoy Star AI! 🚀", parse_mode="Markdown")
        else:
            await query.edit_message_text(
                f"❌ You're not in the group yet. Please join first:\n{GROUP_LINK}\n\nThen click Verify again.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Join Group", url=GROUP_LINK)],
                    [InlineKeyboardButton("✅ Verify Again", callback_data="verify_group")]
                ])
            )
    except Exception as e:
        logger.error(f"Verification error: {e}")
        await query.edit_message_text(
            "⚠️ Could not verify group membership. Please make sure you've joined the group and try again.\n\n"
            f"Join here: {GROUP_LINK}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Join Group", url=GROUP_LINK)],
                [InlineKeyboardButton("🔄 Retry", callback_data="verify_group")]
            ])
        )

# ---------- Main Brain (with verification check) ----------
async def brain(update, context):
    uid = update.effective_user.id

    # If not verified and not owner – block and show verification
    if not is_verified(uid) and not is_owner(uid):
        await verification_required(update, context)
        return

    text = (update.message.text or "").strip()
    low = text.lower()
    cur = get_voice(uid)
    is_creator = is_owner(uid)

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

    # YouTube search via prefix
    if low.startswith("yt ") or low.startswith("play "):
        q = re.sub(r'^(yt|play)\s+', '', text, flags=re.I).strip()
        if not q:
            await update.message.reply_text("Give song name baka~ `yt faded`")
            return
        await handle_youtube_search(update, context, q)
        return

    # YouTube search via "song" suffix
    song_query = extract_song_query(text)
    if song_query:
        await handle_youtube_search(update, context, song_query)
        return

    # Image generation
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
    user_id = str(uid)
    reply = await get_ai_reply(user_id, display_name, text)
    await update.message.reply_text(reply[:4000])

# ---------- Voice Handler (with verification check) ----------
async def voice_brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # If not verified and not owner – block and show verification
    if not is_verified(uid) and not is_owner(uid):
        await verification_required(update, context)
        return

    chat_id = update.effective_chat.id
    cur = get_voice(uid)
    is_creator = is_owner(uid)
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
        user_id = str(uid)
        reply = await get_ai_reply(user_id, display_name, transcribed)
        audio = await tts_bytes(cur, reply)
        if audio:
            await context.bot.send_voice(chat_id=chat_id, voice=io.BytesIO(audio))
        else:
            await context.bot.send_message(chat_id, reply[:4000])
    except Exception as e:
        logger.error(f"voice error {e}")
        await context.bot.send_message(chat_id, "⚠️ Voice error, try again!")

# ---------- Callback ----------
async def on_button(update, context):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("setvoice:"):
        set_voice(q.from_user.id, q.data.split(":", 1)[1])
        await q.edit_message_text(f"✅ Voice set to **{q.data.split(':',1)[1]}**", parse_mode="Markdown")
    elif q.data == "verify_group":
        await verify_user(update, context)

# ---------- Run Flask ----------
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False)

# ---------- Main Bot ----------
async def main():
    if not TOKEN:
        print("BOT_TOKEN missing")
        return

    # Start Flask thread
    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))
    app.add_handler(CommandHandler("imagine", imagine_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_brain))
    app.add_handler(MessageHandler(filters.TEXT, brain))

    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    print(f"✅ Bot Live! Voice->Voice | Text->Text | Image Gen | YouTube Search | Group Verification")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())