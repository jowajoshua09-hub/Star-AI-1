import os, re, json, asyncio, threading, aiohttp, urllib.parse, logging
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from personality import get_system_prompt, CONTACT_BUTTON, GROUP_BUTTON

logging.basicConfig(level=logging.INFO)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROK_URL = os.getenv("GROK_URL")
GEMINI_URL = os.getenv("GEMINI_URL")
IMG_URL = os.getenv("IMG_URL", "https://image.pollinations.ai/prompt/{p}")
VIDEO_URL = os.getenv("VIDEO_URL")
MEMORY_FILE = "memory.json"
memory = {}

def load_memory():
    global memory
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f: memory = json.load(f)
        except: memory = {}
def save_memory():
    try:
        with open(MEMORY_FILE, "w") as f: json.dump(memory, f)
    except: pass
def remember_user(user):
    uid = str(user.id); name = user.first_name or "friend"
    if uid not in memory or memory[uid].get("name")!=name:
        memory[uid] = {"name": name}; save_memory()
    return name

def is_owner_q(t): return any(k in t.lower() for k in ["owner","developer","creator","who made you"])
def get_owner_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton(CONTACT_BUTTON["text"], url=CONTACT_BUTTON["url"])],[InlineKeyboardButton(GROUP_BUTTON["text"], url=GROUP_BUTTON["url"])]])
def is_image(t): return bool(re.search(r'\b(generate|create|make|draw).*(image|pic|photo|wallpaper)\b|\b(image|pic) of\b', t.lower()))
def is_video_request(t): return bool(re.search(r'\b(generate video|make video)\b', t.lower()))
def clean_prompt(t):
    p = re.sub(r'^(generate|create|make|draw|give me)\s+(an? )?(image|video|pic|photo)\s+(of\s+)?', '', t, flags=re.I)
    return p.strip() or t

async def get_ai_reply(user_name, msg):
    payload = f"{get_system_prompt(user_name)}\n\nUser {user_name}: {msg}\nStar AI:"
    for url in [GROK_URL, GEMINI_URL]:
        if not url: continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json={"message": payload}, timeout=20) as r:
                    if r.status == 200:
                        j = await r.json()
                        res = j.get("result") or j.get("response") or j.get("reply")
                        if res and len(str(res).strip()) > 2: return str(res).strip()
        except Exception as e:
            print(f"AI fail {url}: {e}"); continue
    return f"Yo {user_name}! I'm here 🔥 How can I help? Try `generate image of cyberpunk cat`"

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = remember_user(update.effective_user)
    print(f"/start from {user_name}")
    await update.message.reply_text(f"Hey {user_name} 🔥 I'm Star AI by StarDev-il!\n\nSay anything or try:\n`generate image of cyberpunk cat`\n\nNo 404s, just vibes ✨", parse_mode="Markdown")

async def brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    user_name = remember_user(update.effective_user)
    print(f"Message from {user_name}: {text}")

    if is_video_request(text):
        await update.message.reply_text(f"Hey {user_name}, videos coming soon ⚡ Try: generate image of {clean_prompt(text)}")
        return

    placeholder = await update.message.reply_text(f"✨ Hey {user_name}, thinking...")
    try:
        if is_image(text):
            prompt = clean_prompt(text)
            await placeholder.edit_text(f"🎨 Cooking: {prompt[:60]}...")
            encoded = urllib.parse.quote(prompt)
            img_url = IMG_URL.format(p=encoded) if "{p}" in IMG_URL else f"{IMG_URL}/{encoded}"
            await placeholder.delete()
            await context.bot.send_chat_action(update.effective_chat.id, "upload_photo")
            await update.message.reply_photo(photo=img_url, caption=f"For you {user_name} 👇 {prompt}", reply_markup=get_owner_buttons() if is_owner_q(text) else None)
            return
        reply = await get_ai_reply(user_name, text)
        await placeholder.edit_text(reply[:4000], reply_markup=get_owner_buttons() if is_owner_q(text) else None)
    except Exception as e:
        print(f"Brain error: {e}")
        try: await placeholder.edit_text(f"Oops {user_name}, lagged, try again? 😅")
        except: pass

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Star AI by StarDev-il Running OK"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def main():
    load_memory()
    if not TOKEN:
        print("BOT_TOKEN missing!"); return
    threading.Thread(target=run_flask, daemon=True).start()
    # drop_pending_updates=True fixes the "hi does nothing" bug
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT, brain)) # removed ~COMMAND filter
    print("Star AI Ready", flush=True)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    print("Polling started ✅ Send hi now", flush=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
