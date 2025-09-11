# world264_realtime2.py
import os, time, argparse
from datetime import date, timedelta
from typing import List, Tuple
from dotenv import load_dotenv

import format_world264_range as fw  # ใช้ของเดิมที่คุณดึงได้ปกติ

load_dotenv()

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
RECIPIENTS = [s.strip() for s in os.getenv("LINE_GROUP_IDS", "").split(",") if s.strip()]

# -------- LINE push (ตรง ๆ) --------
try:
    from line_messaging import line_multicast
    HAVE_HELPER = True
except Exception:
    HAVE_HELPER = False
    import httpx

def line_push(text: str):
    if not RECIPIENTS:
        print("[WARN] no recipients (LINE_GROUP_IDS)"); return
    if HAVE_HELPER:
        try:
            line_multicast(RECIPIENTS, text); print("✅ sent by helper"); return
        except Exception as e:
            print("[WARN] helper failed -> http:", e)
    if not TOKEN:
        print("[ERR] no LINE_CHANNEL_ACCESS_TOKEN"); return
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    body = lambda to, t: {"to": to, "messages":[{"type":"text","text": t[:4900]}]}
    with httpx.Client(timeout=20) as c:  # type: ignore
        for gid in RECIPIENTS:
            r = c.post("https://api.line.me/v2/bot/message/push", headers=headers, json=body(gid, text))
            print("[push]", gid, r.status_code, r.text[:160])

# -------- WORLD264 helpers --------
Row = Tuple[int, str, str, str]  # (round, hhmm, top3, bot2)

def has_result(t: Row) -> bool:
    return bool((t[2] or "").strip()) and bool((t[3] or "").strip())

def fetch_rows_for(d: date) -> List[Row]:
    """
    ดึงผ่านฟังก์ชันใน format_world264_range.py เท่านั้น (ของคุณดึงได้จริง)
    กรองเฉพาะรอบที่ครบผล แล้ว 'เรียงตามเลขรอบ' เสมอ
    """
    data = fw.fetch_json(d)            # ← ใช้ของเดิม
    key  = fw.pick_world264_key(data)  # ← ใช้ของเดิม
    if not key: return []
    rows = [t for t in fw.extract_rows(data, key) if has_result(t)]
    rows.sort(key=lambda t: t[0])
    return rows

def build_message(rows, limit: int = 40, add_footer: bool = True) -> str:
    # คงลำดับจากรอบน้อย -> มาก และตัดแค่ N รอบล่าสุด
    rows = sorted(rows, key=lambda t: t[0])[-max(1, limit):]

    lines = ["🟢World Lotto 5นาที🟢\n"
             "➖➖➖➖➖➖➖"]
    for idx, (rn, hhmm, top3, bot2) in enumerate(rows, start=1):
        lines.append(f"{rn:>3}: {hhmm} ➡️ {top3} - {bot2}")
        if idx % 4 == 0:
            lines.append("➖➖➖➖➖➖➖")

    # ฟุตเตอร์สรุปผลรอบล่าสุด ตามฟอร์แมตที่ต้องการ
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

# -------- main loop --------
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
            # บางวันไฟล์อาจยังไม่พร้อมช่วงตี 0 → ลองถอยไปวันก่อนชั่วคราว
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
                        line_push(build_message(window, limit))
                        last_sent_round = window[-1][0]
                        print(f"[SEND] force up to round={last_sent_round}")

                # รอบใหม่ = รอบที่หมายเลขมากกว่า last_sent_round เท่านั้น
                new_rows = [t for t in rows_all if t[0] > last_sent_round]
                if new_rows:
                    # กันซ้ำ/กันลำดับเพี้ยน
                    seen = {t[0] for t in window}
                    new_rows = [t for t in new_rows if t[0] not in seen]
                    new_rows.sort(key=lambda t: t[0])

                    if new_rows:
                        window.extend(new_rows)
                        window = sorted(window, key=lambda t: t[0])[-limit:]
                        line_push(build_message(window, limit))
                        last_sent_round = window[-1][0]
                        print(f"[SEND] up to round={last_sent_round}")

        except Exception as e:
            print("[ERR]", e)

        # เปลี่ยนวัน → รีเซ็ต
        if date.today() != cur_day:
            cur_day = date.today()
            last_sent_round = 0
            window = []
            print("[DBG] new day → reset")

        time.sleep(poll)

if __name__ == "__main__":
    main()
