# world264_realtime3.py
# -*- coding: utf-8 -*-
"""
WORLD264 realtime → ส่งเข้า Telegram / LINE
รูปแบบข้อความ: ล็อคบล็อก 4 รอบเสมอ (1–4, 5–8, 9–12, ...)
บล็อกเก่าไม่ขยับ ไม่เลื่อนเป็นหน้าต่าง

ENV ที่อ่าน (อันไหนไม่ตั้ง จะไม่ส่งช่องทางนั้น)
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_IDS            (คั่นหลาย id ด้วย ,)
- LINE_CHANNEL_ACCESS_TOKEN
- LINE_GROUP_IDS               (คั่นหลาย id ด้วย ,)
- TZ / POLL_SEC (ออปชัน)
"""

import os
import time
import argparse
from datetime import date, timedelta
from typing import List, Tuple

from dotenv import load_dotenv
import format_world264_range as fw   # ต้องมีไฟล์นี้อยู่ข้าง ๆ

load_dotenv()

# -------- Settings / ENV ----------
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHATS    = [s.strip() for s in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if s.strip()]

LINE_TOKEN  = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_TO     = [s.strip() for s in os.getenv("LINE_GROUP_IDS", "").split(",") if s.strip()]

Row = Tuple[int, str, str, str]  # (round, hh:mm, top3, bot2)


# -------- Senders ----------
def send_telegram(text: str):
    if not (TG_TOKEN and TG_CHATS): return
    import httpx
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    with httpx.Client(timeout=20) as c:  # type: ignore
        for chat in TG_CHATS:
            try:
                r = c.post(url, data={
                    "chat_id": chat,
                    "text": text[:4000],
                    "disable_web_page_preview": True
                })
                if r.status_code != 200:
                    print("[TG]", chat, r.status_code, r.text[:160])
            except Exception as e:
                print("[TG-ERR]", chat, e)

def send_line(text: str):
    if not (LINE_TOKEN and LINE_TO): return
    import httpx
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    with httpx.Client(timeout=20) as c:  # type: ignore
        for to in LINE_TO:
            try:
                r = c.post("https://api.line.me/v2/bot/message/push",
                           headers=headers,
                           json={"to": to, "messages": [{"type": "text", "text": text[:4900]}]})
                if r.status_code != 200:
                    print("[LINE]", to, r.status_code, r.text[:160])
            except Exception as e:
                print("[LINE-ERR]", to, e)

def send_all(text: str):
    send_telegram(text)
    send_line(text)


# -------- Fetch rows ----------
def has_result(t: Row) -> bool:
    return bool((t[2] or "").strip()) and bool((t[3] or "").strip())

def fetch_rows_for(d: date) -> List[Row]:
    data = fw.fetch_json(d)
    key  = fw.pick_world264_key(data)
    if not key: return []
    rows = [t for t in fw.extract_rows(data, key) if has_result(t)]
    rows.sort(key=lambda t: t[0])
    return rows


# -------- Build message (locked 4-round blocks) ----------
def build_message_locked(rows: List[Row], add_footer: bool = True) -> str:
    """
    คั่นบล็อกตายตัวทุก 4 รอบ — บล็อกเก่าไม่เลื่อน:
    1–4, 5–8, 9–12, ...
    """
    if not rows:
        return "🟢World Lotto 5นาที🟢\n(ยังไม่มีผล)"

    rows = sorted(rows, key=lambda t: t[0])

    lines: List[str] = ["🟢World Lotto 5นาที🟢"]
    current_block = None  # index ของบล็อก (0 เริ่มที่รอบ 1–4)

    for rn, hhmm, top3, bot2 in rows:
        block_id = (rn - 1) // 4
        if block_id != current_block:
            # ปิด/เปิดคั่นเฉพาะเมื่อเข้า block ใหม่
            lines.append("➖➖➖➖➖➖➖")
            current_block = block_id
        lines.append(f"{rn:>3}: {hhmm} ➡️ {top3} - {bot2}")

    # ปิดบล็อกสุดท้าย
    lines.append("➖➖➖➖➖➖➖")

    if add_footer:
        rn, hhmm, top3, bot2 = rows[-1]
        lines += [
            "🟢World Lotto 5นาที🟢",
            f"       264world รอบที่ {rn}",
            f"            {top3} - {bot2}",
            "➖➖➖➖➖➖➖",
        ]
    return "\n".join(lines)


# -------- Main loop ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=int(os.getenv("POLL_SEC", "20")))
    ap.add_argument("--force", action="store_true", help="ส่งครั้งแรกทันที")
    args = ap.parse_args()

    poll = max(5, args.poll)

    today = date.today()
    last_sent_round = 0  # กันส่งซ้ำ

    print(f"[START] day={today} poll={poll}s  (locked blocks)")

    while True:
        try:
            # บางวันไฟล์อาจมาช้า → ลองถอยไปวันก่อน
            rows_all: List[Row] = []
            for d in (today, today - timedelta(days=1)):
                try:
                    rows_all = fetch_rows_for(d)
                    if rows_all:
                        break
                except Exception as e:
                    print(f"[DBG] fetch {d} failed:", e)

            if rows_all:
                if args.force and last_sent_round == 0:
                    send_all(build_message_locked(rows_all))
                    last_sent_round = rows_all[-1][0]
                    print(f"[SEND] init up to round={last_sent_round}")

                # มีรอบใหม่หรือไม่
                if rows_all[-1][0] > last_sent_round:
                    send_all(build_message_locked(rows_all))
                    last_sent_round = rows_all[-1][0]
                    print(f"[SEND] up to round={last_sent_round}")

        except Exception as e:
            print("[ERR]", e)

        # วันที่เปลี่ยน → รีเซ็ต state
        if date.today() != today:
            today = date.today()
            last_sent_round = 0
            print("[DBG] new day → reset")

        time.sleep(poll)


if __name__ == "__main__":
    main()
