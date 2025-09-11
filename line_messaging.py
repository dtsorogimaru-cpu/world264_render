import os, httpx
from typing import Iterable
from dotenv import load_dotenv

load_dotenv()
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

PROXIES = {}
if os.getenv("HTTP_PROXY"): PROXIES["http://"] = os.getenv("HTTP_PROXY")
if os.getenv("HTTPS_PROXY"): PROXIES["https://"] = os.getenv("HTTPS_PROXY")

def _client():
    if PROXIES:
        return httpx.Client(timeout=15, proxies=PROXIES)
    return httpx.Client(timeout=15)

def line_push(to_id: str, text: str):
    if not CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN missing")
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"to": to_id, "messages": [{"type":"text","text": text[:4900]}]}
    with _client() as c:
        r = c.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json() if r.content else {"ok": True}

def line_multicast(ids: Iterable[str], text: str):
    for _id in ids:
        try:
            line_push(_id, text)
        except Exception as e:
            print("[push-fail]", _id, e)
