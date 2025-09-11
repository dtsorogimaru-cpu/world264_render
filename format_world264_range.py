
import httpx, sys, json
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
    BKK = ZoneInfo("Asia/Bangkok")
except Exception:
    BKK = timezone(timedelta(hours=7))

BASE = "https://ltx-s3-prod.s3.ap-southeast-1.amazonaws.com/lotto-result-list/{d}.json"

def z3(x): return "" if x is None else str(x).strip().zfill(3)
def z2(x): return "" if x is None else str(x).strip().zfill(2)

def fetch_json(d: date) -> dict | None:
    url = BASE.format(d=d.strftime("%Y-%m-%d"))
    with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent":"world264-formatter/1.0"}) as c:
        r = c.get(url)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return None
        return None

def pick_world264_key(day_data: dict) -> str | None:
    # ใช้ subtype '22' และจำนวนรอบ >= 200 เป็นหลัก, fallback เป็น '0122'
    for gk, rounds in (day_data or {}).items():
        if not isinstance(rounds, dict) or not rounds: 
            continue
        sample = next(iter(rounds.values()))
        if sample.get("lotto_type") == "01" and sample.get("lotto_subtype") == "22" and len(rounds) >= 200:
            return gk
    return "0122" if day_data and "0122" in day_data else None

def extract_rows(day_data: dict, world_key: str):
    rows = []
    for rec in (day_data.get(world_key) or {}).values():
        res = rec.get("result") or {}
        rn = int(rec.get("round_number") or 0)
        end_at = rec.get("end_at")
        hhmm = ""
        if end_at:
            try:
                dt = datetime.fromisoformat(end_at)
                hhmm = dt.astimezone(BKK).strftime("%H:%M")
            except Exception:
                hhmm = ""
        rows.append((rn, hhmm, z3(res.get("top_three")), z2(res.get("bottom_two"))))
    return sorted(rows, key=lambda r: r[0])

def format_day_text(d: date, rows):
    out = []
    out.append("เวิลลอตโต้5นาที")
    out.append("➖➖➖➖➖➖➖")
    out.append("🟢World Lotto 5นาที🟢")
    out.append("➖➖➖➖➖➖➖")
    for rn, hhmm, top3, bot2 in rows:
        out.append(f"{rn:>3}: {hhmm} ➡️ {top3} - {bot2}")
        if rn % 4 == 0:
            out.append("➖➖➖➖➖➖➖")
    if rows:
        last_rn, _, last_top3, last_bot2 = rows[-1]
        out.append("🟢World Lotto 5นาที🟢")
        out.append(f"      264world รอบที่ {last_rn}      ")
        out.append(f"            {last_top3} - {last_bot2} ")
        out.append("➖➖➖➖➖➖➖")
    return "\n".join(out)

def write_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8")

def run_range(days: int = 7, out_dir: Path = Path("./world264_texts")):
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(tz=BKK).date()
    written = 0
    for i in range(days):
        d = today - timedelta(days=i)
        data = fetch_json(d)
        if not data:
            continue
        key = pick_world264_key(data)
        if not key:
            continue
        rows = extract_rows(data, key)
        txt = format_day_text(d, rows)
        write_text(out_dir / f"world264_{d:%Y-%m-%d}.txt", txt)
        written += 1
    print(f"Wrote {written} day(s) to", out_dir)

if __name__ == "__main__":
    # ใช้: python format_world264_range.py [days]
    # ถ้าไม่ใส่ จะดึงย้อนหลัง 7 วัน
    days = 7
    if len(sys.argv) > 1:
        try:
            days = max(1, int(sys.argv[1]))
        except Exception:
            pass
    run_range(days=days)
