import requests
from bs4 import BeautifulSoup
import json
import re

SEEN_FILE = "data/seen_posts.json"


def load_seen():
    with open(SEEN_FILE) as f:
        return set(json.load(f))


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-500:], f)


def parse_channel(channel: str) -> list:
    url = f"https://t.me/s/{channel}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        posts = []
        for msg in soup.select(".tgme_widget_message"):
            post_id = msg.get("data-post", "")
            text_el = msg.select_one(".tgme_widget_message_text")
            text = text_el.get_text("\n") if text_el else ""
            img = msg.select_one(".tgme_widget_message_photo_wrap")
            photo_url = None
            if img:
                style = img.get("style", "")
                m = re.search(r"url\('(.+?)'\)", style)
                if m:
                    photo_url = m.group(1)
            posts.append({
                "id": post_id,
                "channel": channel,
                "text": text,
                "photo": photo_url,
                "url": f"https://t.me/{post_id}",
            })
        return posts
    except Exception as e:
        print(f"Ошибка парсинга {channel}: {e}")
        return []


def get_new_posts(channels: list, keywords: list) -> list:
    seen = load_seen()
    new_posts = []
    for ch in channels:
        for post in parse_channel(ch):
            if post["id"] in seen:
                continue
            if keywords:
                text_lower = post["text"].lower()
                if not any(kw.lower() in text_lower for kw in keywords):
                    continue
            new_posts.append(post)
            seen.add(post["id"])
    save_seen(seen)
    return new_posts
