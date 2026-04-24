from __future__ import annotations

import os
import re
import html
import time
import json
import sqlite3
import hashlib
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BASE_URL = "https://pokecawatch.com"
CATEGORY_URL = "https://pokecawatch.com/category/%E6%8A%BD%E9%81%B8%E3%83%BB%E4%BA%88%E7%B4%84%E6%83%85%E5%A0%B1"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "300"))

# Se RUN_ONCE=1, il bot fa un solo controllo e poi termina.
# Utile per GitHub Actions / cron giornaliero.
RUN_ONCE = os.getenv("RUN_ONCE", "0").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

# Consiglio: tieni 3 per evitare espansioni vecchie.
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "3"))

SEND_ON_FIRST_RUN = os.getenv("SEND_ON_FIRST_RUN", "0").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

DEBUG = os.getenv("DEBUG", "1").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

# Invia solo lotterie realmente aperte ora.
ACTIVE_ONLY = os.getenv("ACTIVE_ONLY", "1").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

# Di default NON invia upcoming.
NOTIFY_UPCOMING = os.getenv("NOTIFY_UPCOMING", "0").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

# Se una scadenza senza anno e senza data di inizio è troppo lontana,
# viene ignorata per evitare vecchie raffle interpretate come future.
END_ONLY_MAX_DAYS_AHEAD = int(os.getenv("END_ONLY_MAX_DAYS_AHEAD", "21"))

# Se 1, per date senza inizio accetta solo scadenze nel mese corrente.
STRICT_CURRENT_MONTH = os.getenv("STRICT_CURRENT_MONTH", "0").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "2"))
MESSAGE_DELAY_SECONDS = float(os.getenv("MESSAGE_DELAY_SECONDS", "3"))
TRANSLATION_DELAY_SECONDS = float(os.getenv("TRANSLATION_DELAY_SECONDS", "0.7"))

TRANSLATE_ENABLED = os.getenv("TRANSLATE_ENABLED", "1").strip().lower() in {
    "1", "true", "yes", "si", "sì"
}

MAX_TRANSLATION_CHARS = int(os.getenv("MAX_TRANSLATION_CHARS", "120"))

DB_PATH = os.getenv("DB_PATH", "data/sent_lotteries.db")

JST = ZoneInfo("Asia/Tokyo")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class Article:
    title: str
    url: str
    expansion_jp: str


@dataclass
class DateWindow:
    raw: str
    start: datetime | None
    end: datetime | None
    is_expired: bool
    is_upcoming: bool
    is_open_now: bool
    label_en: str


@dataclass
class LotteryItem:
    expansion_jp: str
    expansion_en: str

    place_jp: str
    place_en: str

    area_jp: str
    area_en: str

    raffle_type: str

    date_raw: str
    date_en: str

    start_iso: str | None
    end_iso: str | None

    status: str

    lottery_url: str | None
    source_url: str


# ============================================================
# PREFECTURES / COMMON TRANSLATIONS
# ============================================================

PREFECTURES = {
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県",
    "沖縄県",
}

COMMON_TRANSLATIONS = {
    "オンライン": "Online",
    "オンライン / website": "Online / website",
    "店舗": "Physical stores",
    "各都道府県の店舗": "Stores by prefecture",

    "ポケモンセンターオンライン": "Pokémon Center Online",
    "ヤマダ電機": "Yamada Denki",
    "あみあみ": "AmiAmi",
    "エディオン": "Edion",
    "セブンネットショッピング": "Seven Net Shopping",
    "イオンスタイルオンライン": "AEON STYLE Online",
    "ホビーステーション": "Hobby Station",
    "トイザらス": "Toys R Us",
    "ドラゴンスター": "Dragon Star",
    "GEO": "GEO",
    "Amazon": "Amazon",

    "北海道": "Hokkaido",
    "青森県": "Aomori",
    "岩手県": "Iwate",
    "宮城県": "Miyagi",
    "秋田県": "Akita",
    "山形県": "Yamagata",
    "福島県": "Fukushima",
    "茨城県": "Ibaraki",
    "栃木県": "Tochigi",
    "群馬県": "Gunma",
    "埼玉県": "Saitama",
    "千葉県": "Chiba",
    "東京都": "Tokyo",
    "神奈川県": "Kanagawa",
    "新潟県": "Niigata",
    "富山県": "Toyama",
    "石川県": "Ishikawa",
    "福井県": "Fukui",
    "山梨県": "Yamanashi",
    "長野県": "Nagano",
    "岐阜県": "Gifu",
    "静岡県": "Shizuoka",
    "愛知県": "Aichi",
    "三重県": "Mie",
    "滋賀県": "Shiga",
    "京都府": "Kyoto",
    "大阪府": "Osaka",
    "兵庫県": "Hyogo",
    "奈良県": "Nara",
    "和歌山県": "Wakayama",
    "鳥取県": "Tottori",
    "島根県": "Shimane",
    "岡山県": "Okayama",
    "広島県": "Hiroshima",
    "山口県": "Yamaguchi",
    "徳島県": "Tokushima",
    "香川県": "Kagawa",
    "愛媛県": "Ehime",
    "高知県": "Kochi",
    "福岡県": "Fukuoka",
    "佐賀県": "Saga",
    "長崎県": "Nagasaki",
    "熊本県": "Kumamoto",
    "大分県": "Oita",
    "宮崎県": "Miyazaki",
    "鹿児島県": "Kagoshima",
    "沖縄県": "Okinawa",
}

_TRANSLATION_CACHE: dict[str, str] = {}


# ============================================================
# BASIC UTILITIES
# ============================================================

def clean_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\u3000", " ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def translate_ja_to_en(text: str) -> str:
    text = clean_text(text)

    if not text:
        return ""

    if text in COMMON_TRANSLATIONS:
        return COMMON_TRANSLATIONS[text]

    if text in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[text]

    if not TRANSLATE_ENABLED or len(text) > MAX_TRANSLATION_CHARS:
        _TRANSLATION_CACHE[text] = text
        return text

    try:
        from deep_translator import GoogleTranslator

        time.sleep(TRANSLATION_DELAY_SECONDS)
        translated = GoogleTranslator(source="ja", target="en").translate(text)
        translated = clean_text(translated) if translated else text
    except Exception:
        translated = text

    _TRANSLATION_CACHE[text] = translated
    return translated


def get_soup(url: str) -> BeautifulSoup:
    time.sleep(REQUEST_DELAY_SECONDS)

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def clean_expansion_title(title: str) -> str:
    title = clean_text(title)

    replacements = [
        "〖ポケカ〗",
        "【ポケカ】",
        "ポケカ",
        "抽選・予約情報",
        "抽選情報",
        "予約情報",
    ]

    for value in replacements:
        title = title.replace(value, "")

    title = title.strip(" ｜|-　")
    return clean_text(title)


def format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def is_online_area(area_jp: str) -> bool:
    area_jp = clean_text(area_jp)
    return area_jp in {"オンライン", "オンライン / website"} or "オンライン" in area_jp


def get_raffle_type(area_jp: str) -> str:
    if is_online_area(area_jp):
        return "Online website"

    return "Physical in-store"


def extract_lottery_url(article_url: str, cell) -> str | None:
    link_tag = cell.find("a", href=True)

    if not link_tag:
        return None

    href = clean_text(link_tag.get("href", ""))

    if not href:
        return None

    if href.startswith("#"):
        return None

    return urljoin(article_url, href)


# ============================================================
# DATABASE
# ============================================================

def init_db() -> None:
    folder = os.path.dirname(DB_PATH)

    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sent (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def already_sent(item_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id FROM sent WHERE id = ?", (item_id,))
    row = cur.fetchone()

    conn.close()
    return row is not None


def mark_sent(item_id: str, item: LotteryItem) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO sent (id, payload) VALUES (?, ?)",
        (item_id, json.dumps(item.__dict__, ensure_ascii=False)),
    )

    conn.commit()
    conn.close()


def is_first_run() -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM sent")
    count = cur.fetchone()[0]

    conn.close()
    return count == 0


# ============================================================
# DATE PARSER
# ============================================================

DATE_RE = re.compile(
    r"(?:(?P<year>\d{4})[/-])?"
    r"(?P<month>\d{1,2})[/-]"
    r"(?P<day>\d{1,2})"
    r"(?:\s*(?P<hour>\d{1,2}):(?P<minute>\d{2}))?"
)


def normalize_date_text(text: str) -> str:
    text = clean_text(text)

    text = text.replace("〜", "～")
    text = text.replace("－", "～")
    text = text.replace("—", "～")
    text = text.replace("–", "～")

    text = re.sub(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", r"\1/\2/\3", text)
    text = re.sub(r"(\d{1,2})月\s*(\d{1,2})日", r"\1/\2", text)

    text = re.sub(r"(\d{1,2})時\s*(\d{2})分?", r"\1:\2", text)
    text = re.sub(r"(\d{1,2})時$", r"\1:00", text)

    text = text.replace("午前", "")
    text = text.replace("午後", "")

    return clean_text(text)


def infer_best_year(month: int, day: int, hour: int, minute: int, now: datetime) -> int:
    candidates: list[tuple[float, int]] = []

    for year in [now.year - 1, now.year, now.year + 1]:
        try:
            candidate = datetime(year, month, day, hour, minute, tzinfo=JST)
        except ValueError:
            continue

        diff_seconds = abs((candidate - now).total_seconds())
        candidates.append((diff_seconds, year))

    if not candidates:
        return now.year

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def build_datetime_from_match(
    match: re.Match,
    now: datetime,
    is_end: bool,
) -> datetime | None:
    year_raw = match.group("year")

    month = int(match.group("month"))
    day = int(match.group("day"))

    hour_raw = match.group("hour")
    minute_raw = match.group("minute")

    if hour_raw is None:
        hour = 23 if is_end else 0
        minute = 59 if is_end else 0
    else:
        hour = int(hour_raw)
        minute = int(minute_raw)

    if year_raw:
        year = int(year_raw)
    else:
        year = infer_best_year(month, day, hour, minute, now)

    try:
        return datetime(year, month, day, hour, minute, tzinfo=JST)
    except ValueError:
        return None


def parse_date_window(raw_date: str) -> DateWindow | None:
    raw_date = clean_text(raw_date)

    if not raw_date:
        return None

    invalid_words = [
        "販売分",
        "発売日",
        "発売",
        "価格",
        "収録",
        "BOX",
        "パック",
        "円",
    ]

    if any(word in raw_date for word in invalid_words):
        return None

    normalized = normalize_date_text(raw_date)
    matches = list(DATE_RE.finditer(normalized))

    if not matches:
        return None

    now = datetime.now(JST)

    start_dt: datetime | None = None
    end_dt: datetime | None = None

    has_range = "～" in normalized and len(matches) >= 2
    has_any_explicit_year = any(match.group("year") for match in matches)

    if has_range:
        start_dt = build_datetime_from_match(matches[0], now, is_end=False)
        end_dt = build_datetime_from_match(matches[1], now, is_end=True)
    else:
        end_dt = build_datetime_from_match(matches[-1], now, is_end=True)

    if end_dt is None:
        return None

    if start_dt is not None and start_dt > end_dt:
        try:
            end_dt = end_dt.replace(year=end_dt.year + 1)
        except ValueError:
            return None

    # Filtro anti-date ambigue senza anno.
    # Esempio: siamo ad aprile e appare "7/20まで".
    # Senza anno potrebbe essere una vecchia riga interpretata come futura.
    if not has_any_explicit_year and not has_range:
        days_ahead = (end_dt - now).total_seconds() / 86400

        if STRICT_CURRENT_MONTH and end_dt.month != now.month:
            return None

        if days_ahead > END_ONLY_MAX_DAYS_AHEAD:
            return None

    is_expired = now > end_dt
    is_upcoming = start_dt is not None and now < start_dt
    is_open_now = not is_expired and not is_upcoming

    if start_dt and end_dt:
        label = f"from {format_dt(start_dt)} to {format_dt(end_dt)} JST"
    else:
        label = f"until {format_dt(end_dt)} JST"

    return DateWindow(
        raw=raw_date,
        start=start_dt,
        end=end_dt,
        is_expired=is_expired,
        is_upcoming=is_upcoming,
        is_open_now=is_open_now,
        label_en=label,
    )


# ============================================================
# ARTICLE FETCHING
# ============================================================

def fetch_article_links() -> list[Article]:
    soup = get_soup(CATEGORY_URL)

    articles: list[Article] = []
    seen: set[str] = set()

    for link in soup.select("h1 a, h2 a, h3 a, article a"):
        title = clean_text(link.get_text(" ", strip=True))
        href = link.get("href")

        if not title or not href:
            continue

        if "抽選・予約情報" not in title:
            continue

        url = urljoin(BASE_URL, href)

        if url in seen:
            continue

        seen.add(url)

        articles.append(
            Article(
                title=title,
                url=url,
                expansion_jp=clean_expansion_title(title),
            )
        )

    return articles[:MAX_ARTICLES]


# ============================================================
# TABLE PARSER
# ============================================================

def is_area_row(place_text: str, date_text: str) -> bool:
    place_text = clean_text(place_text)
    date_text = clean_text(date_text)

    if place_text in PREFECTURES:
        return True

    if "各都道府県の店舗" in place_text:
        return True

    if place_text in {"オンライン情報", "オンライン", "店舗"}:
        return True

    if place_text in {"オンライン情報", "オンライン", "店舗"} and date_text in {"締め切り", "締切"}:
        return True

    return False


def update_area_from_row(place_text: str, current_area: str) -> str:
    place_text = clean_text(place_text)

    if place_text in PREFECTURES:
        return place_text

    if "各都道府県の店舗" in place_text:
        return "店舗"

    if place_text in {"オンライン情報", "オンライン"}:
        return "オンライン / website"

    if place_text == "店舗":
        return "店舗"

    return current_area


def should_skip_place(place_text: str, date_text: str) -> bool:
    place_text = clean_text(place_text)
    date_text = clean_text(date_text)

    if not place_text:
        return True

    if place_text in {"オンライン情報", "締め切り", "締切", "scadenza", "情報"}:
        return True

    if any(x in place_text for x in ["楽天", "Yahoo"]):
        if not date_text:
            return True

    if place_text == "Amazon" and not date_text:
        return True

    return False


def extract_rows_from_table(
    article: Article,
    table,
    current_area: str,
) -> tuple[list[LotteryItem], str, dict[str, int]]:
    items: list[LotteryItem] = []

    stats = {
        "open_now": 0,
        "expired": 0,
        "upcoming": 0,
        "invalid": 0,
    }

    rows = table.find_all("tr")

    for tr in rows:
        cells = tr.find_all(["td", "th"])

        if len(cells) == 1:
            single_text = clean_text(cells[0].get_text(" ", strip=True))

            if is_area_row(single_text, ""):
                current_area = update_area_from_row(single_text, current_area)

            continue

        if len(cells) < 2:
            continue

        place_text = clean_text(cells[0].get_text(" ", strip=True))
        date_text = clean_text(cells[1].get_text(" ", strip=True))

        if is_area_row(place_text, date_text):
            current_area = update_area_from_row(place_text, current_area)
            continue

        if should_skip_place(place_text, date_text):
            continue

        lottery_url = extract_lottery_url(article.url, cells[0])

        date_window = parse_date_window(date_text)

        if date_window is None:
            stats["invalid"] += 1
            continue

        if date_window.is_expired:
            stats["expired"] += 1
            continue

        if date_window.is_upcoming:
            stats["upcoming"] += 1

            if ACTIVE_ONLY or not NOTIFY_UPCOMING:
                continue

        if ACTIVE_ONLY and not date_window.is_open_now:
            continue

        status = "Active"

        if date_window.is_upcoming:
            status = "Upcoming"

        raffle_type = get_raffle_type(current_area)

        item = LotteryItem(
            expansion_jp=article.expansion_jp,
            expansion_en=translate_ja_to_en(article.expansion_jp),

            place_jp=place_text,
            place_en=translate_ja_to_en(place_text),

            area_jp=current_area,
            area_en=translate_ja_to_en(current_area),

            raffle_type=raffle_type,

            date_raw=date_text,
            date_en=date_window.label_en,

            start_iso=date_window.start.isoformat() if date_window.start else None,
            end_iso=date_window.end.isoformat() if date_window.end else None,

            status=status,

            lottery_url=lottery_url,
            source_url=article.url,
        )

        items.append(item)
        stats["open_now"] += 1

    return items, current_area, stats


def find_lottery_section_heading(container):
    heading_tags = ["h2", "h3", "h4", "h5"]

    for tag in container.find_all(heading_tags):
        text = clean_text(tag.get_text(" ", strip=True))

        if text == "抽選・予約情報":
            return tag

    return None


def merge_stats(total: dict[str, int], partial: dict[str, int]) -> None:
    for key, value in partial.items():
        total[key] = total.get(key, 0) + value


def extract_lottery_rows(article: Article) -> tuple[list[LotteryItem], dict[str, int]]:
    soup = get_soup(article.url)

    container = (
        soup.select_one(".entry-content")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.body
        or soup
    )

    start_heading = find_lottery_section_heading(container)

    items: list[LotteryItem] = []
    current_area = "オンライン / website"

    stats = {
        "open_now": 0,
        "expired": 0,
        "upcoming": 0,
        "invalid": 0,
    }

    if start_heading is not None:
        heading_tags = ["h2", "h3", "h4", "h5"]

        for sibling in start_heading.find_next_siblings():
            if getattr(sibling, "name", None) in heading_tags:
                heading_text = clean_text(sibling.get_text(" ", strip=True))

                if any(stop in heading_text for stop in ["発売済み", "発売予定", "関連記事", "コメント"]):
                    break

            if not hasattr(sibling, "find_all"):
                continue

            if sibling.name == "table":
                tables = [sibling]
            else:
                tables = sibling.find_all("table")

            for table in tables:
                table_items, current_area, table_stats = extract_rows_from_table(
                    article,
                    table,
                    current_area,
                )

                items.extend(table_items)
                merge_stats(stats, table_stats)

    # Fallback: cerca qualunque tabella con colonna 締め切り.
    if not items and stats["expired"] == 0 and stats["upcoming"] == 0 and stats["invalid"] == 0:
        for table in container.find_all("table"):
            table_text = clean_text(table.get_text(" ", strip=True))

            if "締め切り" not in table_text and "締切" not in table_text:
                continue

            table_items, current_area, table_stats = extract_rows_from_table(
                article,
                table,
                current_area,
            )

            items.extend(table_items)
            merge_stats(stats, table_stats)

    unique: dict[str, LotteryItem] = {}

    for item in items:
        key = (
            f"{item.expansion_jp}|"
            f"{item.place_jp}|"
            f"{item.area_jp}|"
            f"{item.date_raw}|"
            f"{item.lottery_url or ''}"
        )
        unique[key] = item

    return list(unique.values()), stats


# ============================================================
# TELEGRAM
# ============================================================

def make_item_id(item: LotteryItem) -> str:
    raw = "|".join(
        [
            item.expansion_jp,
            item.place_jp,
            item.area_jp,
            item.raffle_type,
            item.date_raw,
            item.lottery_url or "",
            item.source_url,
        ]
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_message(item: LotteryItem) -> str:
    expansion_line = item.expansion_en
    if item.expansion_en != item.expansion_jp:
        expansion_line = f"{item.expansion_en} / {item.expansion_jp}"

    place_line = item.place_en
    if item.place_en != item.place_jp:
        place_line = f"{item.place_en} / {item.place_jp}"

    area_line = item.area_en
    if item.area_en != item.area_jp:
        area_line = f"{item.area_en} / {item.area_jp}"

    raffle_link_block = ""

    if item.raffle_type == "Online website":
        if item.lottery_url:
            raffle_link_block = f'\n🔗 <b>Link Raffle:</b> <a href="{html.escape(item.lottery_url)}">Open raffle page</a>'
        else:
            raffle_link_block = "\n🔗 <b>Link Raffle:</b> Not available"

    message = f"""
🎯 <b>New Pokémon TCG JP Lottery</b>

📦 <b>Expansion name:</b>
{html.escape(expansion_line)}

📍 <b>Lottery place/site:</b>
{html.escape(place_line)}

🏷️ <b>Raffle type:</b>
{html.escape(item.raffle_type)}

🗾 <b>Area:</b>
{html.escape(area_line)}

🗓️ <b>Date:</b>
{html.escape(item.date_en)}

📌 <b>Status:</b>
{html.escape(item.status)}
{raffle_link_block}

📰 <a href="{html.escape(item.source_url)}">Pokecawatch source</a>
""".strip()

    return message


def send_telegram_message(item: LotteryItem) -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")

    if not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID in .env")

    message = build_message(item)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    while True:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )

        if response.status_code == 429:
            try:
                retry_after = response.json().get("parameters", {}).get("retry_after", 10)
            except Exception:
                retry_after = 10

            wait_time = int(retry_after) + 2
            print(f"Telegram Too Many Requests. Attendo {wait_time} secondi...")
            time.sleep(wait_time)
            continue

        if not response.ok:
            raise RuntimeError(f"Telegram error: {response.status_code} - {response.text}")

        time.sleep(MESSAGE_DELAY_SECONDS)
        break


# ============================================================
# MAIN CHECK
# ============================================================

def check_once() -> tuple[int, int, int, int, int]:
    first_run = is_first_run()

    articles = fetch_article_links()

    if DEBUG:
        print(f"Articoli trovati: {len(articles)}")
        for article in articles:
            print(f"- {article.expansion_jp} | {article.url}")

    total_open_now = 0
    total_upcoming = 0
    total_expired = 0
    total_invalid = 0
    total_sent = 0

    for article in articles:
        try:
            rows, stats = extract_lottery_rows(article)
        except Exception as exc:
            print(f"Errore parsing articolo {article.url}: {exc}")
            continue

        total_open_now += len(rows)
        total_upcoming += stats.get("upcoming", 0)
        total_expired += stats.get("expired", 0)
        total_invalid += stats.get("invalid", 0)

        if DEBUG:
            print(
                f"{article.expansion_jp}: "
                f"{len(rows)} attive ora inviabili, "
                f"{stats.get('upcoming', 0)} upcoming ignorate, "
                f"{stats.get('expired', 0)} scadute ignorate, "
                f"{stats.get('invalid', 0)} righe non valide"
            )

        for item in rows:
            item_id = make_item_id(item)

            if already_sent(item_id):
                continue

            if first_run and not SEND_ON_FIRST_RUN:
                mark_sent(item_id, item)
                continue

            try:
                send_telegram_message(item)
                mark_sent(item_id, item)
                total_sent += 1

                print(
                    f"Inviata: {item.expansion_jp} | "
                    f"{item.place_jp} | {item.raffle_type} | "
                    f"{item.date_raw} | {item.status}"
                )

            except Exception as exc:
                print(f"Errore invio Telegram: {exc}")

    return total_open_now, total_upcoming, total_expired, total_invalid, total_sent


# ============================================================
# MAIN LOOP
# ============================================================

def print_startup_info() -> None:
    print("Bot avviato.")
    print(f"Database: {DB_PATH}")
    print(f"Modalità esecuzione singola RUN_ONCE: {'sì' if RUN_ONCE else 'no'}")
    print(f"Controllo ogni {CHECK_EVERY_SECONDS} secondi.")
    print(f"Max articoli/espansioni analizzate: {MAX_ARTICLES}")
    print(f"Invio al primo avvio: {'sì' if SEND_ON_FIRST_RUN else 'no'}")
    print(f"Solo lotterie attive ora: {'sì' if ACTIVE_ONLY else 'no'}")
    print(f"Invio upcoming: {'sì' if NOTIFY_UPCOMING else 'no'}")
    print(f"Filtro mese corrente stretto: {'sì' if STRICT_CURRENT_MONTH else 'no'}")
    print(f"Max giorni avanti per scadenze senza inizio: {END_ONLY_MAX_DAYS_AHEAD}")
    print(f"Delay richieste sito: {REQUEST_DELAY_SECONDS}s")
    print(f"Delay messaggi Telegram: {MESSAGE_DELAY_SECONDS}s")
    print(f"Delay traduzione: {TRANSLATION_DELAY_SECONDS}s")
    print(f"Traduzione attiva: {'sì' if TRANSLATE_ENABLED else 'no'}")
    print(f"Debug: {'sì' if DEBUG else 'no'}")


def print_result(open_now: int, upcoming: int, expired: int, invalid: int, sent: int) -> None:
    print(
        "Controllo completato. "
        f"Attive ora inviabili: {open_now}. "
        f"Upcoming ignorate: {upcoming}. "
        f"Scadute ignorate: {expired}. "
        f"Righe non valide: {invalid}. "
        f"Nuove inviate: {sent}."
    )


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Manca TELEGRAM_BOT_TOKEN nel file .env o nei secrets")

    if not CHAT_ID:
        raise RuntimeError("Manca TELEGRAM_CHAT_ID nel file .env o nei secrets")

    init_db()
    print_startup_info()

    if RUN_ONCE:
        try:
            open_now, upcoming, expired, invalid, sent = check_once()
            print_result(open_now, upcoming, expired, invalid, sent)
        except Exception as exc:
            print(f"Errore generale: {exc}")
            raise

        return

    while True:
        try:
            open_now, upcoming, expired, invalid, sent = check_once()
            print_result(open_now, upcoming, expired, invalid, sent)

        except KeyboardInterrupt:
            print("Bot fermato.")
            break

        except Exception as exc:
            print(f"Errore generale: {exc}")

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()