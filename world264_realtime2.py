# world264_realtime3.py
# -*- coding: utf-8 -*-
"""
WORLD264 realtime → ส่งเข้า Telegram / LINE
- จัดข้อความแบบ "ล็อกบล็อก 4 รอบ": 1–4, 5–8, 9–12, ...
- กันส่งซ้ำด้วย last_sent_round
- Telegram: จำกัดแสดง 50 รอบล่าสุด (เพื่อไม่ชนข้อจำกัดความยาวข้อความของ Telegram)
- LINE: ส่งได้ทั้งวันตามปกติ (ถ้าต้องการจำกัดเหมือนกันให้ตั้ง LIMIT_LINE_ROUNDS ใน ENV ได้)

ENV:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_IDS              (คั่นหลาย id ด้วย ,)
  LINE_CHANNEL_ACCESS_TOKEN
  LINE_GROUP_IDS                 (คั่นหลาย id ด้วย ,)
  POLL_SEC (ออปชัน, default 20)
  LIMIT_TG_ROUNDS (ออปชัน, default 50)
  LIMIT_LINE_ROUNDS (ออปชัน, ไม่ตั้ง = ส่งเต็ม)
"""

import os
import time
import argparse
from datetime import date, timedelta
from typing import List, Tuple

from dotenv import load_dotenv
import format_world264_range as fw   # ต้องมีไฟล์นี้อยู่

load_dotenv()

# -------- Settings / ENV ----------
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHATS    = [s.strip() for s in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if s.strip()]

LINE_TOKEN  = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_TO     = [s.strip() for s in os.getenv("LINE_GROUP_IDS", "").split(",") if s.strip()]

LIMIT_TG    = int(os.getenv("LIMIT_TG_ROUNDS", "50"))     # << จำกัด Telegram 50 รอบ
LIMIT_LINE  = os.getenv("LIMIT_LINE_ROUNDS", "").strip()
LIMIT_LINE  = int(LIMIT_LINE) if LIMIT_LINE.isdigit() else None

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
                    "text": text[:4000],  # TG ~4096
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


# -------- Helper: slice ล่าสุด N รอบ และจัดให้เริ่มต้นที่ต้นบล็อก (4 รอบ) --------
def slice_last_n_aligned(rows: List[Row], n: int) -> List[Row]:
    """
    ตัดเอา 'n รอบล่าสุด' แต่จะ **ขยับจุดเริ่ม** ให้ตรงต้นบล็อก (1–4, 5–8, …)
    เพื่อให้คั่นเส้นออกมาเป็นบล็อก 4 รายการสวยงาม
    """
    if not rows or n <= 0:
        return []

    rows = sorted(rows, key=lambda t: t[0])
    max_round = rows[-1][0]
    start_round = max_round - n + 1
    # ปรับให้ไปที่ 'หัวบล็อก'
    start_round = ((start_round - 1) // 4) * 4 + 1
    # ไม่ให้ต่ำกว่ารอบแรกที่มี
    min_round = rows[0][0]
    if start_round < min_round:
        start_round = min_round
    return [t for t in rows if t[0] >= start_round]


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
            lines.append("➖➖➖➖➖➖➖")
            current_block = block_id
        lines.append(f"{rn:>3}: {hhmm} ➡️ {top3} - {bot2}")

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


# -------- สร้างข้อความแยกตามช่องทาง --------
def build_for_telegram(rows_all: List[Row]) -> str:
    limited = slice_last_n_aligned(rows_all, LIMIT_TG)
    return build_message_locked(limited, add_footer=True)

def build_for_line(rows_all: List[Row]) -> str:
    if LIMIT_LINE:
        limited = slice_last_n_aligned(rows_all, LIMIT_LINE)
        return build_message_locked(limited, add_footer=True)
    # ไม่จำกัด → ส่งทั้งวัน
    return build_message_locked(rows_all, add_footer=True)


# -------- Main loop ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=int(os.getenv("POLL_SEC", "20")))
    ap.add_argument("--force", action="store_true", help="ส่งครั้งแรกทันที")
    args = ap.parse_args()

    poll = max(5, args.poll)

    today = date.today()
    last_sent_round = 0  # กันส่งซ้ำ

    print(f"[START] day={today} poll={poll}s  (locked blocks, TG limit {LIMIT_TG} rounds)")

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
                    # ส่งแยกตามช่องทาง
                    tg_text = build_for_telegram(rows_all)
                    ln_text = build_for_line(rows_all)
                    if TG_TOKEN and TG_CHATS: send_telegram(tg_text)
                    if LINE_TOKEN and LINE_TO: send_line(ln_text)
                    last_sent_round = rows_all[-1][0]
                    print(f"[SEND] init up to round={last_sent_round}")

                # มีรอบใหม่หรือไม่
                if rows_all[-1][0] > last_sent_round:
                    tg_text = build_for_telegram(rows_all)
                    ln_text = build_for_line(rows_all)
                    if TG_TOKEN and TG_CHATS: send_telegram(tg_text)
                    if LINE_TOKEN and LINE_TO: send_line(ln_text)
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
