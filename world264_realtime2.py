# world264_realtime3.py
# -*- coding: utf-8 -*-
"""
ดึงผล WORLD264 แบบ realtime แล้วส่งสรุปไป Telegram/LINE
- คั่นผลแบบ "แช่แข็ง" ทีละ 4 รอบ: 1–4, 5–8, 9–12, ...
- กันรอบซ้ำด้วย last_sent_round
- ใช้ตัวดึงข้อมูลจาก format_world264_range.py ของคุณ
"""

import os
import time
import argparse
from datetime import date, timedelta
from typing import List, Tuple

from dotenv import load_dotenv

# ====== นำตัวดึงข้อมูลของคุณมาใช้ (ดึงได้จริง) ======
# ต้องมีไฟล์ format_world264_range.py อยู่ข้าง ๆ ไฟล์นี้
import format_world264_range as fw  # fetch_json(d), pick_world264_key(data), extract_rows(data, key)

load_dotenv()

# ------------- ENV / CONFIG -------------
# Telegram (ถ้าไม่ตั้งไว้ จะไม่ส่ง)
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# รองรับหลาย chat id คั่นด้วย ,
TG_CHAT_IDS = [s.strip() for s in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if s.strip()]

# LINE (ถ้าไม่ตั้งไว้ จะไม่ส่ง)
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_TO_IDS = [s.strip() for s in os.getenv("LINE_GROUP_IDS", "").split(",") if s.strip()]

# ------------- Types -------------
Row = Tuple[int, str, str, str]  # (round, hh:mm, top3, bot2)


# ------------- ส่งข้อความ -------------
def send_telegram(text: str) -> None:
    if not (TG_TOKEN and TG_CHAT_IDS):
        return
    import httpx
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = lambda chat_id: {
        "chat_id": chat_id,
        "text": text[:4000],  # TG limit ~4096
        "disable_web_page_preview": True,
        "parse_mode": "HTML",  # ใช้ plain ก็ได้
    }
    with httpx.Client(timeout=20) as c:  # type: ignore
        for chat in TG_CHAT_IDS:
            try:
                r = c.post(url, data=payload(chat))
                if r.status_code != 200:
                    print("[TG]", chat, r.status_code, r.text[:160])
            except Exception as e:
                print("[TG-ERR]", chat, e)


def send_line(text: str) -> None:
    if not (LINE_TOKEN and LINE_TO_IDS):
        return
    import httpx
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    body = lambda to: {"to": to, "messages": [{"type": "text", "text": text[:4900]}]}
    with httpx.Client(timeout=20) as c:  # type: ignore
        for gid in LINE_TO_IDS:
            try:
                r = c.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body(gid))
                if r.status_code != 200:
                    print("[LINE]", gid, r.status_code, r.text[:160])
            except Exception as e:
                print("[LINE-ERR]", gid, e)


def send_all(text: str) -> None:
    # ส่งเฉพาะช่องทางที่ตั้ง ENV ไว้
    send_telegram(text)
    send_line(text)


# ------------- WORLD264 helpers -------------
def has_result(t: Row) -> bool:
    # มีทั้ง top3 และ bottom2
    return bool((t[2] or "").strip()) and bool((t[3] or "").strip())


def fetch_rows_for(d: date) -> List[Row]:
    """ใช้งาน format_world264_range ของคุณให้ดึง/แปลงผล แล้วกรองเฉพาะที่มีผล"""
    data = fw.fetch_json(d)                 # ← ใช้ของเดิม
    key = fw.pick_world264_key(data)        # ← ใช้ของเดิม
    if not key:
        return []
    rows = [t for t in fw.extract_rows(data, key) if has_result(t)]
    rows.sort(key=lambda t: t[0])           # เรียงตามรอบ
    return rows


# ------------- Build message (แบบแช่แข็ง 4 รอบต่อบล็อก) -------------
def build_message(rows: List[Row], add_footer: bool = True) -> str:
    """
    แสดงผลแบบ 'แช่แข็ง' ทีละ 4 รอบเสมอ:
    1–4, 5–8, 9–12, ... โดยคั่นด้วย '➖➖➖➖➖➖➖'
    """
    rows = sorted(rows, key=lambda t: t[0])

    lines = ["🟢World Lotto 5นาที🟢"]
    block: List[str] = []

    for i, (rn, hhmm, top3, bot2) in enumerate(rows, start=1):
        block.append(f"{rn:>3}: {hhmm} ➡️ {top3} - {bot2}")
        # ครบ 4 รายการ → ปิดบล็อกทันที
        if i % 4 == 0:
            lines.append("➖➖➖➖➖➖➖")
            lines.extend(block)
            lines.append("➖➖➖➖➖➖➖")
            block = []

    # กรณียังไม่ครบ 4 รายการในบล็อกสุดท้าย
    if block:
        lines.append("➖➖➖➖➖➖➖")
        lines.extend(block)
        lines.append("➖➖➖➖➖➖➖")

    # ฟุตเตอร์สรุปรอบล่าสุด (optional)
    if add_footer and rows:
        rn, hhmm, top3, bot2 = rows[-1]
        footer = (
            "➖➖➖➖➖➖➖\n"
            "🟢World Lotto 5นาที🟢\n"
            f"       264world รอบที่ {rn}      \n"
            f"            {top3} - {bot2} \n"
            "➖➖➖➖➖➖➖"
        )
        lines.append(footer)

    return "\n".join(lines)


# ------------- Main loop -------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=int(os.getenv("POLL_SEC", "20")))
    ap.add_argument("--limit", type=int, default=int(os.getenv("WINDOW_SIZE", "40")))
    ap.add_argument("--force", action="store_true", help="ส่งครั้งแรกทันทีด้วยหน้าต่างล่าสุด")
    args = ap.parse_args()

    poll = max(5, args.poll)
    limit = max(1, args.limit)

    cur_day = date.today()
    last_sent_round = 0
    window: List[Row] = []

    print(f"[START] day={cur_day} poll={poll}s limit={limit}")

    while True:
        try:
            # เผื่อไฟล์วันใหม่ยังไม่อัป ขอลองถอยไปวันก่อน
            try_days = [cur_day, cur_day - timedelta(days=1)]
            rows_all: List[Row] = []
            for d in try_days:
                try:
                    rows_all = fetch_rows_for(d)
                    if rows_all:
                        break
                except Exception as e:
                    print(f"[DBG] fetch {d} failed:", e)

            if rows_all:
                # init window
                if not window:
                    window = rows_all[-limit:]
                    if args.force:
                        send_all(build_message(window))
                        last_sent_round = window[-1][0]
                        print(f"[SEND] force up to round={last_sent_round}")

                # หา "รอบใหม่" ที่มากกว่า last_sent_round
                new_rows = [t for t in rows_all if t[0] > last_sent_round]
                if new_rows:
                    # กันซ้ำ + เรียง
                    seen = {t[0] for t in window}
                    new_rows = [t for t in new_rows if t[0] not in seen]
                    new_rows.sort(key=lambda t: t[0])

                    if new_rows:
                        window.extend(new_rows)
                        # คงเฉพาะ N รอบล่าสุด
                        window = sorted(window, key=lambda t: t[0])[-limit:]
                        send_all(build_message(window))
                        last_sent_round = window[-1][0]
                        print(f"[SEND] up to round={last_sent_round}")

        except Exception as e:
            print("[ERR]", e)

        # ข้ามเป็นวันใหม่ → reset กล่องจำ
        if date.today() != cur_day:
            cur_day = date.today()
            last_sent_round = 0
            window = []
            print("[DBG] new day → reset")

        time.sleep(poll)


if __name__ == "__main__":
    main()
