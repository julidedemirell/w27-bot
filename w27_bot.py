#!/usr/bin/env python3
"""
W27 Heilbronn apartment watcher.

Watches https://www.apartments-hn.de/apartment-mieten for apartments that show
"Apply now" and sends a Telegram message (with the direct application link) for
every new one that matches your filters.

Settings come from environment variables (GitHub Secrets / Variables):
  TELEGRAM_BOT_TOKEN   required  bot token from @BotFather
  TELEGRAM_CHAT_ID     required  your chat id
  W27_TYPES            optional  comma list of type substrings, e.g. "Single, balcony,Partner"
                                 (match if the type contains ANY of them; empty = all)
  W27_EXCLUDE_TYPES    optional  comma list of substrings to skip, e.g. "barrier-free,limited furnishing"
  W27_MAX_RENT         optional  e.g. 505.5
  W27_EARLIEST         optional  earliest acceptable move-in date, YYYY-MM-DD
  W27_LATEST           optional  latest acceptable move-in date, YYYY-MM-DD
  RUN_MINUTES          optional  how long one run keeps polling (default 0 = check once)
  POLL_SECONDS         optional  seconds between checks inside a run (default 90)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

LIST_URL = "https://www.apartments-hn.de/apartment-mieten"
STATE_FILE = Path(__file__).parent / "state" / "seen.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

# --------------------------------------------------------------------------- utils

def env_list(name: str) -> list[str]:
    return [s.strip().lower() for s in os.getenv(name, "").split(",") if s.strip()]


def env_float(name: str) -> float | None:
    v = os.getenv(name, "").strip().replace(",", ".")
    return float(v) if v else None


def env_date(name: str) -> date | None:
    v = os.getenv(name, "").strip()
    return date.fromisoformat(v) if v else None


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"seen": {}, "error_notified": False}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


# ------------------------------------------------------------------------ telegram

def telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log("Telegram not configured, message would be:\n" + text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=20,
    )
    if not r.ok:
        log(f"Telegram error {r.status_code}: {r.text[:300]}")


# ------------------------------------------------------------------------- scraper

ROW_JS = """
() => [...document.querySelectorAll('tr.book-property__table-row')].map(tr => {
  const cell = t => (tr.querySelector(`td[data-title^="${t}"]`)?.innerText || '').replace(/\\s+/g,' ').trim();
  const link = tr.querySelector('a[href*="onboarding.reos.software"]');
  return {
    apartment: cell('Apartment'), type: cell('Type'), location: cell('Location'),
    size: cell('Apartment size'), rent: cell('All-inclusive rent'),
    availability: cell('Availability'), link: link ? link.href : null,
  };
})
"""


def fetch_apartments(page) -> list[dict]:
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_selector("tr.book-property__table-row", timeout=60_000)
    page.wait_for_timeout(1500)  # let the client-side table finish
    rows = page.evaluate(ROW_JS)
    if len(rows) < 50:  # the full list has ~200 rows; fewer means the page changed
        raise RuntimeError(f"only {len(rows)} rows found, page layout may have changed")
    return rows


def contract_id(link: str) -> str:
    m = re.search(r"/contract/([0-9a-f]+)/", link)
    return m.group(1) if m else link


def move_in(apt: dict) -> date | None:
    m = re.search(r"\d{4}-\d{2}-\d{2}", apt["availability"])
    return date.fromisoformat(m.group(0)) if m else None


def matches(apt: dict) -> bool:
    t = apt["type"].lower()
    want, skip = env_list("W27_TYPES"), env_list("W27_EXCLUDE_TYPES")
    if want and not any(w in t for w in want):
        return False
    if any(s in t for s in skip):
        return False
    max_rent = env_float("W27_MAX_RENT")
    try:
        if max_rent is not None and float(apt["rent"]) > max_rent:
            return False
    except ValueError:
        pass
    d = move_in(apt)
    earliest, latest = env_date("W27_EARLIEST"), env_date("W27_LATEST")
    if d and earliest and d < earliest:
        return False
    if d and latest and d > latest:
        return False
    return True


def format_msg(apt: dict) -> str:
    d = move_in(apt)
    return (
        "🏠 <b>W27'de yeni daire başvuruya açıldı!</b>\n\n"
        f"<b>{apt['apartment']}</b> · {apt['type']}\n"
        f"📍 {apt['location']} · {apt['size']} m²\n"
        f"💶 {apt['rent']} € (her şey dahil)\n"
        f"📅 Taşınma: {d.isoformat() if d else apt['availability']}\n\n"
        f"👉 <a href=\"{apt['link']}\">Hemen başvur</a>\n"
        f"Zaten kayıtlıysan: <a href=\"https://scs.onboarding.reos.software/login?accomodation={contract_id(apt['link'])}\">Giriş yap ve başvur</a>"
    )


# ---------------------------------------------------------------------------- main

def check_once(page, state: dict) -> None:
    apts = fetch_apartments(page)
    open_now = [a for a in apts if a["link"]]
    log(f"{len(apts)} apartments, {len(open_now)} open for applications")

    if state.get("error_notified"):
        telegram("✅ W27 botu tekrar çalışıyor.")
        state["error_notified"] = False

    open_ids = set()
    for apt in open_now:
        cid = contract_id(apt["link"])
        open_ids.add(cid)
        if cid in state["seen"]:
            continue
        state["seen"][cid] = {"apartment": apt["apartment"], "first_seen":
                              datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if matches(apt):
            log(f"NEW match: {apt['apartment']} {apt['type']} {apt['rent']}")
            telegram(format_msg(apt))
        else:
            log(f"new but filtered out: {apt['apartment']} {apt['type']} {apt['rent']}")

    # forget listings that closed, so a re-opened apartment is announced again
    for cid in list(state["seen"]):
        if cid not in open_ids:
            del state["seen"][cid]


def main() -> int:
    run_minutes = float(os.getenv("RUN_MINUTES", "0") or 0)
    poll = max(30, int(os.getenv("POLL_SECONDS", "90") or 90))
    deadline = time.monotonic() + run_minutes * 60
    state = load_state()
    failures = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=UA, locale="de-DE")
        while True:
            try:
                check_once(page, state)
                failures = 0
            except Exception as e:  # noqa: BLE001
                failures += 1
                log(f"check failed ({failures}): {e}")
                if failures >= 3 and not state.get("error_notified"):
                    telegram(f"⚠️ W27 botu listeyi okuyamıyor: {str(e)[:300]}")
                    state["error_notified"] = True
            save_state(state)
            if time.monotonic() + poll > deadline:
                break
            time.sleep(poll)
        browser.close()
    return 0


if __name__ == "__main__":
    if "--test-telegram" in sys.argv:
        telegram("✅ W27 botu bağlandı. Yeni daire çıkınca buradan haber vereceğim.")
        sys.exit(0)
    sys.exit(main())
