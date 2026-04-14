import re
import os
from html import escape
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.kvkk.gov.tr"
LIST_PAGES = [
    "https://www.kvkk.gov.tr/Icerik/2015/Duyurular",
    "https://www.kvkk.gov.tr/Icerik/2015/Duyurular?page=2",
]

SITE_TITLE = "KVKK Duyurular"
SITE_LINK = "https://www.kvkk.gov.tr/Icerik/2015/Duyurular"
SITE_DESCRIPTION = "Kişisel Verileri Koruma Kurumu - Duyurular"
OUTPUT_FILE = "feed.xml"

MONTHS = {
    "Ocak": 1,
    "Şubat": 2,
    "Mart": 3,
    "Nisan": 4,
    "Mayıs": 5,
    "Haziran": 6,
    "Temmuz": 7,
    "Ağustos": 8,
    "Eylül": 9,
    "Ekim": 10,
    "Kasım": 11,
    "Aralık": 12,
}

DATE_RE = re.compile(
    r"(\d{1,2})\s+"
    r"(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)"
    r"\s+(\d{4})"
)

BLACKLIST_TEXTS = {
    "Anasayfa", "TR", "EN", "DE", "Etkinlikler", "Kütüphane", "İletişim",
    "Kurum Başkanı", "Kurul Üyeleri", "Tarihçe", "Misyon - Vizyon",
    "Stratejik Plan", "Faaliyet Raporu", "Çerez Aydınlatma Metni",
    "Yönetmelikler", "Tebliğler", "Bağlayıcı Şirket Kuralları",
    "Standart Sözleşmeler", "Veri Sorumlusu Kimdir?", "İlgili Kişi Kimdir?",
    "İlgili Kişinin Hakları", "Rehberler", "Diğer Dokümanlar", "KVKK Bülten",
    "Videolar", "Podcast Kanalımız", "«", "»"
}


def parse_tr_date(text: str):
    m = DATE_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS[m.group(2)]
    year = int(m.group(3))
    return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc)


def is_article_link(href: str):
    if not href:
        return False
    if "page=" in href:
        return False
    if "/Icerik/2015/Duyurular" in href:
        return False
    return "/Icerik/" in href


def normalize_text(text: str):
    return " ".join(text.split()).strip()


def extract_items_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    candidates = soup.find_all(["div", "li", "article", "section", "p"])
    for node in candidates:
        text = normalize_text(" ".join(node.stripped_strings))
        if not text:
            continue

        dt = parse_tr_date(text)
        if not dt:
            continue

        anchors = node.find_all("a", href=True)
        anchors = [
            a for a in anchors
            if is_article_link(a.get("href", ""))
        ]

        if not anchors:
            continue

        best_anchor = None
        best_len = 0
        for a in anchors:
            title = normalize_text(a.get_text(" ", strip=True))
            if not title:
                continue
            if title in BLACKLIST_TEXTS:
                continue
            if len(title) > best_len:
                best_len = len(title)
                best_anchor = a

        if not best_anchor:
            continue

        title = normalize_text(best_anchor.get_text(" ", strip=True))
        href = urljoin(BASE_URL, best_anchor["href"])

        if len(title) < 12:
            continue

        items.append({
            "title": title,
            "link": href,
            "pub_date": dt,
        })

    # 去重：按 link 去重
    dedup = {}
    for item in items:
        dedup[item["link"]] = item

    result = list(dedup.values())
    result.sort(key=lambda x: x["pub_date"], reverse=True)
    return result


def fetch(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KVKK-RSS-Bot/1.0)"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def rfc2822_date(dt: datetime):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_feed(items):
    now = datetime.now(timezone.utc)

    rss_items = []
    for item in items[:30]:
        rss_items.append(f"""
        <item>
            <title>{escape(item["title"])}</title>
            <link>{escape(item["link"])}</link>
            <guid isPermaLink="true">{escape(item["link"])}</guid>
            <pubDate>{rfc2822_date(item["pub_date"])}</pubDate>
            <description>{escape(item["title"])}</description>
        </item>
        """.strip())

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape(SITE_TITLE)}</title>
    <link>{escape(SITE_LINK)}</link>
    <description>{escape(SITE_DESCRIPTION)}</description>
    <language>tr</language>
    <lastBuildDate>{rfc2822_date(now)}</lastBuildDate>
    {''.join(rss_items)}
  </channel>
</rss>
"""
    return rss


def main():
    all_items = []
    for url in LIST_PAGES:
        html = fetch(url)
        all_items.extend(extract_items_from_html(html))

    # 再次全局去重
    dedup = {}
    for item in all_items:
        dedup[item["link"]] = item

    items = list(dedup.values())
    items.sort(key=lambda x: x["pub_date"], reverse=True)

    rss = build_feed(items)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"Generated {OUTPUT_FILE} with {len(items[:30])} items.")


if __name__ == "__main__":
    main()
