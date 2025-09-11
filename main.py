# main.py
import os
import threading
from flask import Flask

# === 1) สตาร์ทบอทในเธรดแยก ===
def start_bot():
    # นำเข้าและเรียก main() จาก world264_realtime2.py
    import world264_realtime2 as bot
    bot.main()  # ใช้ฟังก์ชัน main เดิมของคุณเลย

t = threading.Thread(target=start_bot, daemon=True)
t.start()

# === 2) เว็บ keep-alive สำหรับ Render ===
app = Flask(__name__)

@app.get("/")
def health():
    return "World264 bot is alive!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
