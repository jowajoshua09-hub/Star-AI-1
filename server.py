import threading
from api_client import flask_app
from main import main as bot_main
import asyncio

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)

def run_bot():
    asyncio.run(bot_main())

if __name__ == "__main__":
    # Flask in background thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    # Bot in main thread (keeps polling)
    run_bot()
