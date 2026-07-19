import os, re, json, asyncio, threading, aiohttp, urllib.parse, tempfile, base64, io
from dotenv import load_dotenv
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from telegram.constants import ChatAction
from personality import get_system_prompt

try:
    import PyPDF2
    HAS_PDF = True
except:
    HAS_PDF = False

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROK_URL = os.getenv("GROK_URL")
GEMINI_URL = os.getenv("GEMINI_URL")
BASE = "https://api.hostify.indevs.in/api/ai"
YT_SEARCH = "https://api.hostify.indevs.in/api/search/youtube?q={q}"
IMG_URL = os.getenv("IMG_URL", "https://image.pollinations.ai/prompt/{p}")

MEMORY_FILE = "memory.json"
memory = {}
if os.path.exists(MEMORY_FILE):
    try: memory = json.load(open(MEMORY_FILE))
    except: memory = {}
def save():
    try: json.dump(memory, open(MEMORY_FILE,"w"))
    except: pass
def get_voice(uid): return memory.get(str(uid),{}).get("voice","tsundere")
def set_voice(uid, v):
    uid=str(uid)
    if uid not in memory: memory[uid]={}
    memory[uid]["voice"]=v; save()
def remember(u): return u.first_name or "friend"

CANDIDATE_VOICES = ["tsundere","yandere","kuudere","dandere","deredere","himedere","loli","shota","maid","onee","genki","kawaii","shy","cold","tired","angry"]
VOICE_CACHE=[]

async def discover_voices():
    global VOICE_CACHE
    if VOICE_CACHE: return VOICE_CACHE
    for endpoint in [f"{BASE}/voices", f"{BASE}/list", f"{BASE}/models"]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(endpoint, timeout=6) as r:
                    if r.status==200:
                        j=await r.json()
                        lst=j if isinstance(j,list) else j.get("voices") or j.get("data") or j.get("models") or []
                        if lst: VOICE_CACHE=[str(x).lower().strip() for x in lst]; print(f"Voices from {endpoint}: {VOICE_CACHE}"); return VOICE_CACHE
        except: pass
    working=[]
    async with aiohttp.ClientSession() as s:
        for v in CANDIDATE_VOICES:
            try:
                async with s.post(f"{BASE}/{v}", json={"text":"test"}, timeout=5) as r:
                    if r.status in [200,201]: working.append(v)
            except: pass
    VOICE_CACHE = working if working else CANDIDATE_VOICES
    return VOICE_CACHE

async def get_ai_reply(name, msg):
    payload=f"{get_system_prompt(name)}\nUser {name}: {msg}\nStar AI:"
    for url in [GROK_URL, GEMINI_URL]:
        if not url: continue
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json={"message":payload}, timeout=15) as r:
                    if r.status==200:
                        j=await r.json()
                        res=j.get("result") or j.get("response") or j.get("reply")
                        if res and len(str(res).strip())>2: return str(res).strip()
        except: continue
    return f"B-baka {name}! It's not like I wanted to reply..."

async def tts(voice, text):
    url=f"{BASE}/{voice}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"text":text[:300]}, timeout=30) as r:
                if r.headers.get("Content-Type","").startswith("audio"):
                    tmp=tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    tmp.write(await r.read()); tmp.close(); return tmp.name
                data=await r.json()
                audio_url=data.get("audio_url") or data.get("url") or data.get("audio") or data.get("result")
                b64=data.get("base64") or data.get("data")
                if isinstance(b64, dict): b64=b64.get("url") or b64.get("audio")
                if b64 and len(str(b64))>100 and not str(b64).startswith("http"):
                    tmp=tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    tmp.write(base64.b64decode(str(b64).split(",")[-1])); tmp.close(); return tmp.name
                if audio_url and audio_url.startswith("http"):
                    async with s.get(audio_url) as ar:
                        tmp=tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                        tmp.write(await ar.read()); tmp.close(); return tmp.name
                elif audio_url and len(audio_url)>100:
                    tmp=tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    tmp.write(base64.b64decode(audio_url.split(",")[-1])); tmp.close(); return tmp.name
    except Exception as e:
        print(f"TTS {voice} err: {e}")
    return None

async def yt_search(query):
    url=YT_SEARCH.format(q=urllib.parse.quote(query))
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=15) as r:
                print(f"YT {r.status} q={query}")
                if r.status==200:
                    j=await r.json()
                    if isinstance(j, list): return j[:10]
                    if isinstance(j, dict): return j.get("results") or j.get("data") or j.get("videos") or j.get("result") or []
    except Exception as e:
        print(f"YT error: {e}")
    return []

async def show_voices(chat_id, current, context):
    voices=await discover_voices()
    rows=[InlineKeyboardButton(f"{'✅ ' if v==current else ''}{v}", callback_data=f"setvoice:{v}") for v in voices]
    kb=[rows[i:i+3] for i in range(0,len(rows),3)]
    await context.bot.send_message(chat_id, f"🎤 Current: **{current}**\nFound **{len(voices)}** voices - tap to switch:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def start_cmd(update, context):
    voices=await discover_voices()
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await update.message.reply_text(
        f"Hey {remember(update.effective_user)} 🔥\n\n"
        f"🎤 Voices ({len(voices)}): {', '.join(voices[:6])}\n"
        f"🎵 YouTube: `search youtube DJ` / `yt Alan Walker`\n"
        f"📂 Files: Upload txt/pdf/code to read\n"
        f"🎨 Image: `generate image of cyberpunk cat`\n"
        f"🗣️ Voice: `change voice` / `change voice to yandere`\n\n"
        f"Send voice note → I reply in voice!",
        parse_mode="Markdown"
    )

async def brain(update, context):
    text=(update.message.text or "").strip()
    if not text: return
    low=text.lower()
    uid=update.effective_user.id
    current=get_voice(uid)

    # YOUTUBE
    yt_m=re.search(r'^(?:search\s+)?(?:yt|youtube)\s+(.+)$|^(?:search|find)\s+(.+?)\s+(?:on\s+)?(?:yt|youtube)$|^play\s+(.+)$', low)
    if yt_m:
        query=(yt_m.group(1) or yt_m.group(2) or yt_m.group(3) or "").strip()
        if query and len(query)>1:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            msg=await update.message.reply_text(f"🔍 Searching YouTube for **{query}**...", parse_mode="Markdown")
            results=await yt_search(query)
            if not results:
                await msg.edit_text(f"No results for `{query}` 😅"); return
            buttons=[]; txt=f"🎵 **Results for {query}:**\n\n"
            for i,item in enumerate(results[:8],1):
                if isinstance(item, dict):
                    title=item.get("title") or item.get("name") or "Untitled"
                    vid=item.get("videoId") or item.get("id") or item.get("video_id")
                    url=item.get("url") or item.get("link") or (f"https://youtu.be/{vid}" if vid else None)
                    channel=item.get("channel") or item.get("author") or ""
                else: title=str(item); url=None; channel=""
                txt+=f"{i}. **{title[:45]}** {f'- {channel}' if channel else ''}\n"
                if url: buttons.append([InlineKeyboardButton(f"▶️ {title[:25]}", url=url)])
            await msg.edit_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
            return

    if low in ["change voice","set voice","switch voice","voice","my voice","change my voice"]:
        await show_voices(update.effective_chat.id, current, context); return

    m=re.search(r'(?:change|set|use|switch)\s+voice\s*(?:to|as)?\s*([a-z0-9_-]+)', low)
    if m:
        req=m.group(1)
        if req in ["list","menu","voices","show"]: await show_voices(update.effective_chat.id, current, context); return
        voices=await discover_voices()
        if req in voices:
            set_voice(uid, req)
            await update.message.reply_text(f"✅ Changed to **{req}** baka~ Send voice note now!", parse_mode="Markdown"); return
        else:
            await update.message.reply_text(f"`{req}` not found! Real voices:"); await show_voices(update.effective_chat.id, current, context); return

    if low in ["voices","show voices","voice list","list voices","all voices","voice menu","what voices","what voice"]:
        await show_voices(update.effective_chat.id, current, context); return

    if re.search(r'\b(generate|create|make|draw).*(image|pic|photo)\b', low):
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
        prompt=re.sub(r'^(generate|create|make|draw)\s+(an?\s+)?(image|pic|photo)\s+(of\s+)?', '', text, flags=re.I).strip() or text
        img=IMG_URL.format(p=urllib.parse.quote(prompt))
        try: await update.message.reply_photo(photo=img, caption=f"For you 👇 {prompt}")
        except: await update.message.reply_text(img)
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await asyncio.sleep(0.4)
    reply=await get_ai_reply(remember(update.effective_user), text)
    if str(uid) not in memory or "hinted" not in memory[str(uid)]:
        voices=await discover_voices()
        reply+=f"\n\n💡 I have {len(voices)} voices! Say `show voices` | `yt DJ` to search | upload file to read"
        if str(uid) not in memory: memory[str(uid)]={}
        memory[str(uid)]["hinted"]=True; save()
    await update.message.reply_text(reply[:4000])

async def voice_brain(update, context):
    uid=update.effective_user.id
    voice=get_voice(uid)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
    caption=update.message.caption or "cute tsundere reply"
    reply_text=await get_ai_reply(remember(update.effective_user), f"[voice note] {caption} - reply short tsundere 1-2 sentences")
    path=await tts(voice, reply_text)
    if path and os.path.exists(path):
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VOICE)
        await update.message.reply_voice(voice=open(path,'rb'), caption=f"[{voice}] {reply_text[:200]}")
        os.remove(path)
    else:
        await update.message.reply_text(reply_text)

async def file_brain(update, context):
    doc=update.message.document
    if not doc: return
    file_name=doc.file_name or "file"
    ext=file_name.split(".")[-1].lower() if "." in file_name else ""
    if doc.file_size and doc.file_size>10*1024*1024:
        await update.message.reply_text(f"File too big! {doc.file_size/1024/1024:.1f}MB > 10MB"); return
    status=await update.message.reply_text(f"📂 Reading **{file_name}**...", parse_mode="Markdown")
    try:
        tg_file=await context.bot.get_file(doc.file_id)
        file_bytes=io.BytesIO()
        await tg_file.download_to_memory(file_bytes)
        file_bytes.seek(0)
        content=""
        if ext in ["txt","py","js","json","html","css","md","csv","log","env","sh","bat","xml","yaml","yml","ini","ts","jsx","tsx"]:
            content=file_bytes.read().decode('utf-8', errors='ignore')[:15000]
        elif ext=="pdf":
            if not HAS_PDF:
                await status.edit_text("Add `PyPDF2` to requirements.txt to read PDFs"); return
            reader=PyPDF2.PdfReader(file_bytes)
            txts=[]
            for page in reader.pages[:10]:
                try: txts.append(page.extract_text() or "")
                except: continue
            content="\n".join(txts)[:15000]
            if not content.strip(): content="[PDF no extractable text - scanned?]"
        else:
            try:
                content=file_bytes.read().decode('utf-8', errors='ignore')[:10000]
                if len(content.strip())<5: raise Exception("binary")
            except:
                await status.edit_text(f"Can't read `.{ext}` yet. Supported: txt, py, js, json, csv, pdf, code"); return
        if not content.strip():
            await status.edit_text("File empty!"); return
        name=remember(update.effective_user)
        prompt=f"User uploaded file {file_name} ({len(content)} chars):\n---START---\n{content[:12000]}\n---END---\nSummarize/explain this file to {name}. If code, explain what it does. Tsundere but helpful."
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        reply=await get_ai_reply(name, prompt)
        await status.edit_text(f"📄 **{file_name}** ({len(content)} chars)\n\n{reply[:3500]}", parse_mode="Markdown")
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("🎤 Say as voice", callback_data=f"readfile:{doc.file_id}")]])
        await update.message.reply_text("Want voice version?", reply_markup=kb)
    except Exception as e:
        print(f"File err: {e}")
        await status.edit_text(f"Failed: {e}")

async def on_button(update, context):
    q=update.callback_query
    await q.answer()
    data=q.data
    if data.startswith("setvoice:"):
        v=data.split(":",1)[1]; set_voice(q.from_user.id, v)
        await q.edit_message_text(f"✅ Voice set to **{v}**! Send voice note 🎤", parse_mode="Markdown")
    elif data.startswith("readfile:"):
        voice=get_voice(q.from_user.id)
        txt="File summarized above! It's not like I read it for you baka~"
        path=await tts(voice, txt)
        if path:
            await context.bot.send_chat_action(q.message.chat_id, ChatAction.UPLOAD_VOICE)
            await context.bot.send_voice(chat_id=q.message.chat_id, voice=open(path,'rb'))
            os.remove(path)

flask_app=Flask(__name__)
@flask_app.route('/')
def home(): return "Star AI Full Running"
def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))

async def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(setvoice:|readfile:)"))
    app.add_handler(MessageHandler(filters.Document.ALL, file_brain))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_brain))
    app.add_handler(MessageHandler(filters.TEXT, brain))
    print("Full Bot Ready", flush=True)
    await app.initialize(); await app.start()
    await discover_voices()
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__=="__main__":
    asyncio.run(main())
