# world264_realtime2.py  (Telegram version)
import os, time, argparse
from datetime import date, timedelta
from typing import List, Tuple
from dotenv import load_dotenv

import format_world264_range as fw  # ใช้ตัวเดิมของคุณ

load_dotenv()

# ---------- ENV ----------
# โปรดตั้งค่าใน .env:
# TELEGRAM_BOT_TOKEN=123456:ABC...
# TELEGRAM_CHAT_IDS=-1001234567890,123456789
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT_IDS = [s.strip() for s in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if s.strip()]

import httpx

API_BASE = lambda t: f"https://api.telegram.org/bot{t}"

def tg_send(text: str, chat_id: str | int, parse_mode: str | None = None):
    if not TG_TOKEN:
        print("[ERR] no TELEGRAM_BOT_TOKEN"); return None
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],              # กันยาวเกิน
        "disable_web_page_preview": True
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    with httpx.Client(timeout=20) as c:
        r = c.post(f"{API_BASE(TG_TOKEN)}/sendMessage", json=payload)
        if r.status_code == 429:
            wait = r.json().get("parameters", {}).get("retry_after", 1)
            print(f"[429] flood control → sleep {wait}s")
            time.sleep(wait)
            return tg_send(text, chat_id, parse_mode)
        if r.status_code >= 400:
            print(f"[tg_send ERR] {r.status_code} {r.text[:200]}")
            return None
        return r.json()

def tg_edit(chat_id: str | int, message_id: int, new_text: str, parse_mode: str | None = None):
    if not TG_TOKEN:
        print("[ERR] no TELEGRAM_BOT_TOKEN"); return None
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text[:4000],
        "disable_web_page_preview": True
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    with httpx.Client(timeout=20) as c:
        r = c.post(f"{API_BASE(TG_TOKEN)}/editMessageText", json=payload)
        if r.status_code == 429:
            wait = r.json().get("parameters", {}).get("retry_after", 1)
            print(f"[429] flood control (edit) → sleep {wait}s")
            time.sleep(wait)
            return tg_edit(chat_id, message_id, new_text, parse_mode)
        if r.status_code >= 400:
            print(f"[tg_edit WARN] {r.status_code} {r.text[:200]} → fallback send")
            return tg_send(new_text, chat_id, parse_mode)
        return r.json()

def tg_broadcast(text: str, keep_edit: bool = True):
    """
    ส่งหาหลายแชท:
      - รอบแรก: sendMessage แล้วจำ message_id ไว้ (ต่อแชท)
      - รอบถัดไป: editMessageText เพื่อลดสแปม
    """
    if not TG_CHAT_IDS:
        print("[WARN] no TELEGRAM_CHAT_IDS"); return {}

    results = {}
    for cid in TG_CHAT_IDS:
        state = _message_states.get(cid)
        if keep_edit and state and "message_id" in state:
            resp = tg_edit(cid, state["message_id"], text)
            if resp and "result" in resp and "message_id" in resp["result"]:
                state["message_id"] = resp["result"]["message_id"]
                results[cid] = state["message_id"]
        else:
            resp = tg_send(text, cid)
            if resp and "result" in resp and "message_id" in resp["result"]:
                _message_states[cid] = {"message_id": resp["result"]["message_id"]}
                results[cid] = resp["result"]["message_id"]
    return results

_message_states: dict[str | int, dict] = {}

# ---------- WORLD264 helpers ----------
Row = Tuple[int, str, str, str]  # (round, hhmm, top3, bot2)

def has_result(t: Row) -> bool:
    return bool((t[2] or "").strip()) and bool((t[3] or "").strip())

def fetch_rows_for(d: date) -> List[Row]:
    data = fw.fetch_json(d)
    key  = fw.pick_world264_key(data)
    if not key: return []
    rows = [t for t in fw.extract_rows(data, key) if has_result(t)]
    rows.sort(key=lambda t: t[0])
    return rows

def build_message(rows, limit: int = 40, add_footer: bool = True) -> str:
    rows = sorted(rows, key=lambda t: t[0])[-max(1, limit):]

    lines = ["🟢World Lotto 5นาที🟢\n"
             "➖➖➖➖➖➖➖"]
    for idx, (rn, hhmm, top3, bot2) in enumerate(rows, start=1):
        lines.append(f"{rn:>3}: {hhmm} ➡️ {top3} - {bot2}")
        if idx % 4 == 0:
            lines.append("➖➖➖➖➖➖➖")

    if add_footer and rows:
        rn, hhmm, top3, bot2 = rows[-1]
        footer = (
            "➖➖➖➖➖➖➖\n"
            "🟢World Lotto 5นาที🟢\n"
            f"       264world รอบที่ {rn}      \n"
            f"            {top3} - {bot2} \n"
            " ➖➖➖➖➖➖➖"
        )
        lines.append(footer)

    return "\n".join(lines)

# ---------- main loop ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=20)
    ap.add_argument("--limit", type=int, default=35)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    poll  = max(5, args.poll)
    limit = max(1, args.limit)

    cur_day = date.today()
    last_sent_round = 0
    window: List[Row] = []

    print(f"[START] day={cur_day} poll={poll}s limit={limit}")

    while True:
        try:
            try_days = [cur_day, cur_day - timedelta(days=1)]
            rows_all: List[Row] = []
            for d in try_days:
                try:
                    rows_all = fetch_rows_for(d)
                    if rows_all: break
                except Exception as e:
                    print(f"[DBG] fetch {d} failed:", e)

            if rows_all:
                # init
                if not window:
                    window = rows_all[-limit:]
                    if args.force:
                        tg_broadcast(build_message(window, limit))
                        last_sent_round = window[-1][0]
                        print(f"[SEND] force up to round={last_sent_round}")

                # รอบใหม่
                new_rows = [t for t in rows_all if t[0] > last_sent_round]
                if new_rows:
                    seen = {t[0] for t in window}
                    new_rows = [t for t in new_rows if t[0] not in seen]
                    new_rows.sort(key=lambda t: t[0])

                    if new_rows:
                        window.extend(new_rows)
                        window = sorted(window, key=lambda t: t[0])[-limit:]
                        tg_broadcast(build_message(window, limit))
                        last_sent_round = window[-1][0]
                        print(f"[SEND] up to round={last_sent_round}")

        except Exception as e:
            print("[ERR]", e)

        if date.today() != cur_day:
            cur_day = date.today()
            last_sent_round = 0
            window = []
            print("[DBG] new day → reset")

        time.sleep(poll)

if __name__ == "__main__":
    main()
