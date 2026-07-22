import os
import threading
import asyncio
from api_client import flask_app

# Import bot function WITHOUT running Flask inside main.py
from main import main as bot_main

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    # Only run api_client flask, not main.py's flask
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

if __name__ == "__main__":
    # Flask in background
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Bot in main thread - keep alive
    asyncio.run(bot_main())
