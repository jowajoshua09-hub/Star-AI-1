import os, re, json, asyncio, threading, aiohttp, urllib.parse
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from personality import get_system_prompt, CONTACT_BUTTON, GROUP_BUTTON

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
def is_owner_q(t): return any(k in t.lower() for k in ["owner","developer","creator","who made you","who built you","maker","stardev","bani wako","muridzi wako"])
def get_owner_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton(CONTACT_BUTTON["text"], url=CONTACT_BUTTON["url"])],[InlineKeyboardButton(GROUP_BUTTON["text"], url=GROUP_BUTTON["url"])]])
def is_image(t): return bool(re.search(r'\b(generate|create|make|draw).*(image|pic|photo|wallpaper)\b|\b(image|pic) of\b', t.lower()))
def is_video_request(t): return bool(re.search(r'\b(video|clip|reel|movie|generate video)\b', t.lower()))
def clean_prompt(t):
    p = re.sub(r'^(generate|create|make|draw|give me)\s+(an? )?(image|video|pic|photo|clip|reel|wallpaper)\s+(of\s+)?', '', t, flags=re.I)
    return re.sub(r'^(image|video) of\s+', '', p, flags=re.I).strip() or t
async def get_ai_reply(user_name, msg):
    payload = f"{get_system_prompt(user_name)}\n\nUser {user_name}: {msg}\nStar AI:"
    for url in [GROK_URL, GEMINI_URL]:
        if not url: continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json={"message": payload}, timeout=15) as r:
                    if r.status == 200:
                        j = await r.json()
                        res = j.get("result") or j.get("response")
                        if res and len(str(res).strip()) > 2: return str(res).strip()
        except: continue
    return f"Yo {user_name}, I'm a bit slow rn, ask me again in a sec? Got you 🔥"

async def brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    user_name = remember_user(update.effective_user)
    if is_video_request(text):
        await update.message.reply_text(f"Hey {user_name}, I don't do videos for now ⚡ Try: generate image of {clean_prompt(text)}")
        return
    placeholder = await update.message.reply_text(f"✨ Hey {user_name}, thinking...")
    try:
        if is_image(text):
            prompt = clean_prompt(text)
            try:
                await placeholder.edit_text(f"🎨 Cooking for {user_name}: {prompt[:60]}...")
                encoded = urllib.parse.quote(prompt)
                img_url = IMG_URL.format(p=encoded) if "{p}" in IMG_URL else f"{IMG_URL}/{encoded}"
                await placeholder.delete()
                await context.bot.send_chat_action(update.effective_chat.id, "upload_photo")
                await update.message.reply_photo(photo=img_url, caption=f"For you {user_name} 👇 {prompt}", reply_markup=get_owner_buttons() if is_owner_q(text) else None)
            except:
                try: await placeholder.delete()
                except: pass
                await update.message.reply_text(f"Oops {user_name}, can't get that image right now, try another? 😅")
            return
        try:
            reply = await get_ai_reply(user_name, text)
            await placeholder.edit_text(reply[:4000], reply_markup=get_owner_buttons() if is_owner_q(text) else None)
        except:
            await placeholder.edit_text(f"Oops {user_name}, my brain lagged, say again? 😅")
    except:
        try: await placeholder.edit_text(f"Oops {user_name}, tripped, try again?")
        except: pass

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Star AI by StarDev-il Running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

async def main():
    load_memory()
    if not TOKEN:
        print("BOT_TOKEN missing"); return
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, brain))
    print("Star AI Ready - Fixed for Python 3.14")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
