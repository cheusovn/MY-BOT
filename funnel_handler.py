# -*- coding: utf-8 -*-
"""
funnel_handler.py

Логика воронки — вызывается из webhook-обработчика в bot.py.
Поддерживает несколько активных кампаний одновременно.
"""

import json
import logging
import os
import random
import time

import requests

# ─── CONFIG ───────────────────────────────────────────────────────────────────

_DIR = os.path.dirname(os.path.abspath(__file__))
CAMPAIGNS_FILE = os.path.join(_DIR, "campaigns.json")
STATE_FILE     = os.path.join(_DIR, "funnel_state.json")

ACCESS_TOKEN  = os.environ.get("META_TOKEN", "")
IG_ACCOUNT_ID = os.environ.get("IG_BUSINESS_ID", "17841400041927032")
FB_PAGE_ID    = os.environ.get("FB_PAGE_ID",     "1134532123070528")

GRAPH_URL   = "https://graph.facebook.com/v21.0"
THREADS_URL = "https://graph.threads.net/v1.0"

# ─── ФРАЗЫ ────────────────────────────────────────────────────────────────────

IG_COMMENT_REPLIES = [
    "Скинул, проверь личку 🔥",
    "Уже в директе, лови 👇",
    "Отправил! Проверь входящие 📩",
    "Написал в личку, смотри 😉",
    "Директ проверь — там всё 🚀",
    "Отправил в личку, жди 💌",
    "Уже написал тебе 👀",
    "Проверь личку, скинул 🎯",
    "В директе ждёт, смотри 💡",
    "Написал в личку — не пропусти 🙌",
    "Отправил, загляни в директ 📲",
    "Личку проверь — всё там 🔗",
    "Скинул в директ, лови 👊",
    "Уже написал — смотри личку 💎",
    "В директе оставил, проверяй 🎁",
]

FB_THREADS_REPLIES = [
    "Ссылка в шапке профиля 👆",
    "Всё есть в описании профиля 🔗",
    "Смотри ссылку в шапке ☝️",
    "В шапке профиля найдёшь 👀",
    "Ссылка там, в шапке 🙌",
    "Загляни в описание профиля 🔥",
    "Линк в профиле, жми 👆",
    "Смотри шапку — там всё 💡",
    "В шапке профиля оставил ссылку 📌",
    "Иди в профиль, ссылка там 🚀",
    "Жми на профиль → ссылка в описании 🔗",
    "Всё в шапке, не пропусти 👇",
    "Топ материал по ссылке в профиле 🎯",
    "Ссылка в шапке, лови 👊",
    "В профиле найдёшь — ссылка там 💎",
]

# ─── КАМПАНИИ ─────────────────────────────────────────────────────────────────

def load_campaigns() -> list:
    """Загружаем все активные кампании."""
    try:
        if os.path.exists(CAMPAIGNS_FILE):
            return json.loads(open(CAMPAIGNS_FILE, encoding="utf-8").read())
    except Exception as e:
        logging.error(f"load_campaigns error: {e}")
    return []


def find_campaign(text: str) -> dict | None:
    """Ищем кампанию по ключевому слову в тексте комментария."""
    text_lower = text.lower()
    for c in load_campaigns():
        if not c.get("active", True):
            continue
        for kw in c.get("keyword_variants", [c.get("keyword", "")]):
            if kw.lower() in text_lower:
                return c
    return None


# ─── STATE ────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            return json.loads(open(STATE_FILE, encoding="utf-8").read())
    except Exception:
        pass
    return {"processed": [], "dm_sent": [], "subscribed_confirmed": []}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ─── META API HELPERS ─────────────────────────────────────────────────────────

def _token():
    return ACCESS_TOKEN or os.environ.get("META_TOKEN", "")


def api_get(url: str, params: dict = None) -> dict:
    p = {"access_token": _token(), **(params or {})}
    try:
        r = requests.get(url, params=p, timeout=15)
        return r.json()
    except Exception as e:
        logging.error(f"api_get {url}: {e}")
        return {}


def api_post(url: str, data: dict = None, json_data: dict = None) -> dict:
    try:
        if json_data:
            r = requests.post(url, json={**json_data, "access_token": _token()}, timeout=15)
        else:
            r = requests.post(url, data={"access_token": _token(), **(data or {})}, timeout=15)
        return r.json()
    except Exception as e:
        logging.error(f"api_post {url}: {e}")
        return {}


# ─── IG SUBSCRIPTION CHECK ────────────────────────────────────────────────────

def check_ig_follower(user_igsid: str) -> bool:
    """Проверяем подписку. При ошибке прав — пропускаем (graceful = True)."""
    try:
        data = api_get(f"{GRAPH_URL}/{IG_ACCOUNT_ID}/followers", {"fields": "id", "limit": 500})
        if "error" in data:
            logging.warning(f"IG follow check no permission: {data['error'].get('message','')[:60]}")
            return True
        followers = {f["id"] for f in data.get("data", [])}
        pages = 0
        while "paging" in data and "next" in data.get("paging", {}) and pages < 3:
            cursor = data["paging"]["cursors"]["after"]
            data = api_get(f"{GRAPH_URL}/{IG_ACCOUNT_ID}/followers",
                           {"fields": "id", "limit": 500, "after": cursor})
            followers |= {f["id"] for f in data.get("data", [])}
            pages += 1
        return user_igsid in followers
    except Exception as e:
        logging.warning(f"check_ig_follower exception: {e}")
        return True


# ─── REPLY HELPERS ────────────────────────────────────────────────────────────

def reply_ig_comment(comment_id: str, text: str) -> bool:
    r = api_post(f"{GRAPH_URL}/{comment_id}/replies", data={"message": text})
    return "id" in r


def send_ig_dm(user_igsid: str, text: str, quick_reply: bool = False) -> bool:
    msg: dict = {"text": text}
    if quick_reply:
        msg["quick_replies"] = [
            {"content_type": "text", "title": "Я подписался ✅", "payload": "SUBSCRIBED"}
        ]
    r = api_post(f"{GRAPH_URL}/{IG_ACCOUNT_ID}/messages",
                 json_data={"recipient": {"id": user_igsid}, "message": msg})
    return "message_id" in r or "recipient_id" in r


def reply_fb_comment(comment_id: str, text: str) -> bool:
    r = api_post(f"{GRAPH_URL}/{comment_id}/comments", data={"message": text})
    return "id" in r


def reply_threads_post(post_id: str, text: str, threads_user_id: str) -> bool:
    container = api_post(f"{THREADS_URL}/{threads_user_id}/threads",
                         data={"media_type": "TEXT", "text": text, "reply_to_id": post_id})
    if "id" not in container:
        return False
    time.sleep(2)
    r = api_post(f"{THREADS_URL}/{threads_user_id}/threads_publish",
                 data={"creation_id": container["id"]})
    return "id" in r


# ─── ОБРАБОТЧИКИ СОБЫТИЙ ──────────────────────────────────────────────────────

def handle_ig_comment(comment_id: str, text: str, user_id: str, username: str) -> bool:
    """
    Обрабатываем входящий комментарий Instagram.
    Возвращает True если было кодовое слово и мы отреагировали.
    """
    state = load_state()

    if comment_id in state["processed"]:
        return False

    campaign = find_campaign(text)
    if not campaign:
        return False

    logging.info(f"IG comment: кодовое слово '{campaign['keyword']}' от @{username}")

    # 1. Публичный ответ
    reply = random.choice(IG_COMMENT_REPLIES)
    reply_ig_comment(comment_id, reply)
    logging.info(f"IG: ответ: {reply[:40]}")

    time.sleep(1)

    # 2. DM (только один раз на пользователя)
    if user_id and user_id not in state["dm_sent"]:
        dm = (
            f"Привет! 👋\n\n"
            f"Хочешь получить «{campaign['lead_magnet_name']}»?\n\n"
            f"Подпишись на @nikolay_cheusov в Instagram — и дам доступ 🔥\n\n"
            f"После подписки нажми кнопку 👇"
        )
        if send_ig_dm(user_id, dm, quick_reply=True):
            state["dm_sent"].append(user_id)
            logging.info(f"IG: DM отправлен @{username}")

    state["processed"].append(comment_id)
    # Чистим старые записи
    if len(state["processed"]) > 10000:
        state["processed"] = state["processed"][-5000:]
    save_state(state)
    return True


def handle_ig_dm_reply(msg_id: str, text: str, from_id: str) -> bool:
    """
    Обрабатываем входящий DM — реакция на Quick Reply 'Я подписался'.
    Ищем кампанию по dm_sent (у нас нет текста исходного DM, ищем в campaigns первую активную).
    """
    if from_id == IG_ACCOUNT_ID:
        return False

    state = load_state()
    if msg_id in state["processed"]:
        return False

    is_subscribed_reply = (
        "подписал" in text.lower()
        or "subscribed" in text.lower()
        or "✅" in text
        or "SUBSCRIBED" in text
    )
    if not is_subscribed_reply:
        return False

    # Определяем deeplink — ищем по dm_sent кампанию
    # Так как у нас нет привязки user→campaign, берём первую активную кампанию
    # (в будущем можно хранить user→campaign_id в state)
    campaigns = [c for c in load_campaigns() if c.get("active", True)]
    if not campaigns:
        return False

    # Ищем кампанию для этого пользователя — если сохранена
    user_campaigns = state.get("user_campaigns", {})
    campaign_id = user_campaigns.get(from_id)
    campaign = None
    if campaign_id:
        campaign = next((c for c in load_campaigns() if c["id"] == campaign_id), None)
    if not campaign:
        campaign = campaigns[0]  # fallback: первая активная

    logging.info(f"IG DM: пользователь {from_id} нажал 'Я подписался'")

    is_follower = check_ig_follower(from_id)
    if not is_follower:
        remind = (
            "Пока не вижу тебя среди подписчиков 😊\n\n"
            "Подпишись на @nikolay_cheusov и нажми кнопку ещё раз:"
        )
        send_ig_dm(from_id, remind, quick_reply=True)
    else:
        deeplink = campaign["telegram_deeplink"]
        reply = (
            f"Огонь! 🚀\n\n"
            f"Вот твой материал:\n{deeplink}\n\n"
            f"Там нужно подписаться на Telegram-канал — и файл придёт 📲"
        )
        send_ig_dm(from_id, reply)
        state.setdefault("subscribed_confirmed", []).append(from_id)
        logging.info(f"IG DM: deeplink отправлен {from_id}")

    state["processed"].append(msg_id)
    save_state(state)
    return True


def handle_fb_comment(comment_id: str, text: str, username: str) -> bool:
    """Обрабатываем комментарий Facebook."""
    state = load_state()
    if comment_id in state["processed"]:
        return False

    campaign = find_campaign(text)
    if not campaign:
        return False

    logging.info(f"FB comment: кодовое слово '{campaign['keyword']}' от {username}")
    reply = random.choice(FB_THREADS_REPLIES)
    reply_fb_comment(comment_id, reply)

    state["processed"].append(comment_id)
    save_state(state)
    return True


def handle_threads_reply(reply_id: str, text: str, username: str, threads_user_id: str) -> bool:
    """Обрабатываем ответ в Threads."""
    state = load_state()
    if reply_id in state["processed"]:
        return False

    campaign = find_campaign(text)
    if not campaign:
        return False

    logging.info(f"Threads reply: кодовое слово '{campaign['keyword']}' от @{username}")
    reply_text = random.choice(FB_THREADS_REPLIES)
    reply_threads_post(reply_id, reply_text, threads_user_id)

    state["processed"].append(reply_id)
    save_state(state)
    return True
