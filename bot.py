import asyncio
import json
import os
import logging
import random
import string
import time
import base64
import uuid
import aiohttp
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile,
    BufferedInputFile, LabeledPrice, PreCheckoutQuery,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 817730727


def is_admin(uid) -> bool:
    """Владелец-админ — для полного теста бота без лимитов (время, генерации, гейты).
    На обычных пользователей не влияет."""
    try:
        return int(uid) == ADMIN_ID
    except (TypeError, ValueError):
        return False
BOT_USERNAME = "Trueman_ai_bot"
TRIAL_DAY_1 = "https://t.me/+5ep9DPf7eNMzZjdi"
TRIAL_DAY_2 = "https://t.me/+SpoNR-ahkJFiZTJi"

# Уроки курса по дням. Дни 1–2 — бесплатный пробник, дни 3–8 — после оплаты.
COURSE_LINKS = {
    1: TRIAL_DAY_1,
    2: TRIAL_DAY_2,
    3: "https://t.me/+8TYsQliQrsU3YTIy",
    4: "https://t.me/+rZx8KDLDMGc0ZTYy",
    5: "https://t.me/+M77H7C6pvj04Njcy",
    6: "https://t.me/+QUWfICu78RsyMmMy",
    7: "https://t.me/+LljT4Jwm6UIxN2Fi",
    8: "https://t.me/+QBz_MaKNSIY5ZmQy",
}
TOTAL_DAYS = 8
# Следующий день курса открывается после отметки «домашка сделана» и не ранее,
# чем через это время после открытия предыдущего урока (материал должен улечься).
HW_COOLDOWN = 4 * 3600
# Темы дней (можно переименовать под реальное содержание уроков).
DAY_TITLES = {
    3: "Персонажи и сториборды",
    4: "Анимация, движение камеры и ретушь",
    5: "Звук и видео — Suno и Kling",
    6: "Создаём кино на Seedance 2.0",
    7: "Цифровой аватар и GPT-агенты",
    8: "Бонус: продвижение, продажи и фриланс",
}
GIFT_LINK = "https://t.me/syntxaibot?start=aff_817730727"
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/trueman_ai")
MANAGER = "@nikolay_cheusov"
WELCOME_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.jpg")
# Брендовые шапки-баннеры экранов (генерируются scripts/make_banners.py)
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

STUDENTS_COUNT = "347"

# 2-й день курса открывается только спустя это время после старта 1-го дня
# (даём материалу «улечься» — лучше усваивается, выше доходимость).
DAY2_COOLDOWN = 12 * 3600  # секунд

logging.basicConfig(level=logging.INFO)

# Таймаут сессии: при сетевом лаге Amvera↔Telegram запрос отвалится за 30с,
# а не висит минуту, блокируя ответ (число секунд!).
_session = AiohttpSession(timeout=30)
# Принудительный IPv4: на многих облачных хостах (в т.ч. Amvera) попытка IPv6 к
# api.telegram.org зависает и отваливается только по таймауту (TelegramNetworkError).
# Форс AF_INET убирает «happy eyeballs» подвисания и резко снижает таймауты.
try:
    import socket as _socket
    _session._connector_init["family"] = _socket.AF_INET
except Exception as _e:
    logging.warning(f"could not force IPv4 on session: {_e}")
bot = Bot(
    token=BOT_TOKEN,
    session=_session,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher(storage=MemoryStorage())

DATA_DIR = "/data" if os.path.exists("/data") else "."
PROMO_FILE = os.path.join(DATA_DIR, "promo.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SPOTS_FILE = os.path.join(DATA_DIR, "spots.json")


def load_json(file, default=None):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(file, data):
    # Атомарная запись: пишем во временный файл и подменяем, чтобы не оставить битый JSON
    tmp = f"{file}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, file)


promos = load_json(PROMO_FILE)
users = load_json(USERS_FILE)
spots_data = load_json(SPOTS_FILE, {"spots": 23, "updated": time.time()})

# ─── Отложенная запись на диск (debounce) ──────────────────────────────────────────────────────────
# Вместо блокирующей записи всего файла при каждом действии — помечаем "грязным",
# а фоновый flusher раз в пару секунд пишет в отдельном потоке. Event-loop не блокируется.
_dirty = set()


def _mark_dirty(key: str):
    _dirty.add(key)


def save_promos(): _mark_dirty("promos")
def save_users(): _mark_dirty("users")
def save_spots(): _mark_dirty("spots")


def get_spots() -> int:
    return int(spots_data.get("spots", 23))


def tick_spots():
    s = get_spots()
    if s > 3:
        spots_data["spots"] = s - 1
        spots_data["updated"] = time.time()
        save_spots()


def now_ts() -> float:
    return time.time()


def set_stage(uid: str, stage: str):
    if uid in users:
        users[uid]["stage"] = stage
        users[uid][f"{stage}_at"] = now_ts()
        save_users()


def generate_code(name: str) -> str:
    base = ''.join(c.upper() for c in name if c.isalpha())[:4] or "REF"
    while True:
        code = base + ''.join(random.choices(string.digits, k=3))
        if code not in promos:
            return code


# ─── SOCIAL PROOF: ротация живых отзывов ────────────────────────────────────────────────────────

# Честный social proof: агрегированные формулировки без выдуманных имён/городов/точного времени,
# которые легко опровергнуть и потерять доверие. Опираемся на реальные счётчики, где можем.
SOCIAL_PROOF_LINES = [
    "👋 Рядом учатся такие же новички — ты не один",
    "💚 VIP с куратором берут чаще всего: так спокойнее",
    "✨ Сегодня к нам заглянули ещё несколько человек",
    "🎓 Начать можно бесплатно — без карты и обязательств",
    "🌱 Учимся в своём темпе, спешить не нужно",
]


def social_proof() -> str:
    return random.choice(SOCIAL_PROOF_LINES)


GOAL_LABELS = {
    "freelance": "заработок на фрилансе",
    "business": "прокачку бизнеса",
    "curious": "знакомство с AI",
}

GOAL_HOOKS = {
    "freelance": (
        "💸 <b>Хочешь подзаработать на нейросетях?</b>\n\n"
        "Сейчас многие ищут, кто сделает им картинку,\n"
        "ролик или карточку товара. Платят <b>800–2 500 ₽</b>\n"
        "за штуку — а умеют пока единицы.\n\n"
        "Это обычный навык. Ему можно научиться.\n\n"
    ),
    "business": (
        "🏢 <b>Хочешь применить нейросети в своём деле?</b>\n\n"
        "Контент, реклама, тексты — это можно делать\n"
        "самому, быстрее и без подрядчиков:\n\n"
        "▸ меньше тратишь на дизайнеров и копирайтеров\n"
        "▸ больше материалов своими силами\n"
        "▸ быстрее проверяешь идеи\n\n"
    ),
    "curious": (
        "🔍 <b>Просто интересно, как это всё работает?</b>\n\n"
        "Скажу честно: волшебной кнопки нет.\n"
        "Но если уделять час-другой в день,\n"
        "за неделю реально разобраться с нуля.\n"
        "Спокойно, по шагам — я рядом.\n\n"
    ),
}


# ─── ТАРИФЫ (единый источник цен) ───────────────────────────────────────────────────────────────
# rub_old / rub_now — для отображения. stars — цена в Telegram Stars (оплата без ИП/самозанятого).
# Курс ⭐: ≈ 1 Star ≈ 1.7 ₽ (Telegram удерживает комиссию, выплата через Fragment).
TARIFFS = {
    "base": {"label": "📦 Базовый", "old": 5900, "now": 2970, "floor": 1990, "stars": 1750,
             "perks": "Все 7 дней курса + доступ навсегда"},
    "vip":  {"label": "⭐ VIP с куратором", "old": 9900, "now": 4970, "floor": 3470, "stars": 2900,
             "perks": "Все 7 дней + личный куратор + чат 24/7 + бонусы на 6 470 ₽"},
    "pro":  {"label": "🚀 PRO + продвижение", "old": 14900, "now": 7970, "floor": 5970, "stars": 4690,
             "perks": "Всё из VIP + где брать заказы + вирусный контент + SMM + 8-й день"},
    # Бонусный 8-й день (SMM, продвижение, продажи, маркетинг, фриланс).
    # Входит в PRO; для Базового и VIP — докупается отдельно. Фикс-цена (floor=now).
    "day8": {"label": "🚀 День 8 — продвижение и продажи", "old": 2990, "now": 1790, "floor": 1790, "stars": 1100,
             "perks": "Бонусный день: SMM, продвижение, продажи, маркетинг и фриланс"},
    # Технический тариф для проверки боевой оплаты ЮKassa. Доступен только админу
    # через /paytest, в меню тарифов НЕ показывается. После оплаты выдаёт 1-й день.
    "test": {"label": "🧪 Тест-доступ (1 день)", "old": 100, "now": 100, "floor": 100, "stars": 1,
             "perks": "Проверочный платёж — открывает доступ к 1-му дню курса"},
}

# ─── ЮKassa (Telegram Payments) ───────────────────────────────────────────────────────────────────
# Provider token из @BotFather → Payments → ЮKassa. Тестовый содержит ":TEST:".
# Если не задан — кнопка оплаты картой уходит на менеджера (как раньше).
YOOKASSA_TOKEN = os.environ.get("YOOKASSA_PROVIDER_TOKEN", "")
YOOKASSA_TEST = ":TEST:" in YOOKASSA_TOKEN
# Система налогообложения для чека: 1=ОСН, 2=УСН доходы, 3=УСН доходы-расходы,
# 4=ЕНВД, 5=ЕСХН, 6=Патент. По умолчанию — УСН доходы.
YOOKASSA_TAX_SYSTEM = int(os.environ.get("YOOKASSA_TAX_SYSTEM", "2"))

# ─── ЮKassa API (прямая интеграция: СБП, T-Pay, SberPay, карты) ────────────────────────────────────
# Для приёма СБП / T-Pay / SberPay используется прямой API ЮKassa (Basic Auth: shopId:secret_key).
# YOOKASSA_SECRET_KEY — секретный ключ из кабинета ЮKassa (live_... боевой, test_... тестовый).
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID", "1382534")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY", "")
YOOKASSA_API_ENABLED = bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)
YOOKASSA_API_TEST = YOOKASSA_SECRET_KEY.startswith("test_")
# Куда вернуть покупателя после оплаты (https). По умолчанию — обратно в бот.
YOOKASSA_RETURN_URL = os.environ.get("YOOKASSA_RETURN_URL", f"https://t.me/{BOT_USERNAME}")

# ─── АНАЛИТИКА: лог воронки ───────────────────────────────────────────────────────────────────────
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
events_log = load_json(EVENTS_FILE, {"counters": {}, "recent": []})


def track(event: str, uid: str = "", extra: str = ""):
    """Считает события воронки: land_start, day1, day2, tariffs, buy_*, pay_success, referral…"""
    try:
        events_log.setdefault("counters", {})
        events_log["counters"][event] = events_log["counters"].get(event, 0) + 1
        events_log.setdefault("recent", []).append(
            {"e": event, "uid": uid, "x": extra, "t": int(now_ts())})
        events_log["recent"] = events_log["recent"][-500:]
        _mark_dirty("events")
    except Exception:
        pass


# ─── ГЕЙМИФИКАЦИЯ: XP, уровни, стрики, бейджи, квесты ──────────────────────────────────────────────
LEVELS = [
    (0,    "🥉 Новичок"),
    (100,  "🥈 AI-Джуниор"),
    (300,  "🥇 AI-Мастер"),
    (700,  "💎 AI-Профи"),
    (1500, "👑 AI-Гуру"),
]

BADGES = {
    "first_step":   "🚀 Первый шаг",
    "day1_done":    "✅ День 1 пройден",
    "day2_done":    "🔥 День 2 пройден",
    "explorer":     "🎁 Исследователь (забрал подарок)",
    "referrer":     "💸 Амбассадор (есть промокод)",
    "buyer":        "👑 Студент академии",
    "streak3":      "🔥 Серия 3 дня",
    "streak7":      "⚡ Серия 7 дней",
    "challenger":   "🥊 Боец челленджа",
    "lucky":        "🎰 Крутанул колесо удачи",
    "wonder":       "🪄 Первое волшебное фото",
}

XP_RULES = {
    "day1": 10, "day2": 15, "tariffs": 5,
    "free_gift": 5, "referral": 10, "daily": 5, "buy": 0,
    "challenge": 10, "wow": 5,
}

# ─── СКИДКА ЗА ПРОГРЕСС (механика №6): чем больше XP — тем больше личная скидка ──────────────────
# Порог XP → размер скидки в ₽. Скидка "тает" — действует ограниченное время после разблокировки.
DISCOUNT_TIERS = [(100, 500), (300, 1000), (700, 1500)]
DISCOUNT_TTL = 24 * 3600  # сколько живёт разблокированная скидка, сек

# ─── AI ЧЕРЕЗ OPENROUTER (только OpenRouter, без прямых запросов в Google/др.) ──────────────────────
# Один провайдер — OpenRouter. Ключ ТОЛЬКО из окружения (никогда не хардкодим).
# Каскад моделей внутри OpenRouter: сначала бесплатные :free, при лимите/ошибке — дешёвый платный
# резерв. Всё текстовое и короткое (max_tokens мал) → расход минимальный.
#
# Env: OPENROUTER_API_KEY — openrouter.ai
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_EXTRA = {"HTTP-Referer": "https://t.me/Trueman_ai_bot", "X-Title": "True AI Academy"}

# Бесплатные текстовые модели отключены: :free слишком часто отдают 429/404 и только
# добавляют задержку. Текст идём сразу на дешёвый gpt-4o-mini (доли цента за вызов).
AI_FREE_MODELS = []
AI_PAID_RESERVE = "openai/gpt-4o-mini"  # основной (и единственный) текстовый путь


async def _openrouter_call(model: str, system: str, user: str, max_tokens: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    headers.update(OPENROUTER_EXTRA)
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(OPENROUTER_URL, json=payload, headers=headers) as r:
            data = await r.json()
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {str(data)[:200]}")
            return data["choices"][0]["message"]["content"].strip()


async def ai_text(system: str, user: str, max_tokens: int = 350) -> str:
    """Короткий текстовый вызов через OpenRouter: free-модели → дешёвый платный резерв.
    Возвращает None, если ключа нет или всё недоступно (вызывающий делает мягкий fallback)."""
    if not OPENROUTER_KEY:
        return None
    for model in AI_FREE_MODELS + [AI_PAID_RESERVE]:
        try:
            result = await _openrouter_call(model, system, user, max_tokens)
            if result:
                logging.info(f"AI OK via OpenRouter:{model}")
                return result
        except Exception as e:
            logging.warning(f"OpenRouter:{model} failed: {e} → next")
            continue
    logging.error("AI: all OpenRouter models exhausted")
    return None


CHALLENGE_SYSTEM = (
    "Ты — строгий, но поддерживающий наставник курса по нейросетям True AI Academy. "
    "Ученик прислал свой промпт на заданную тему дня. Оцени его как промпт для нейросети. "
    "Ответь на русском СТРОГО в формате (HTML-теги <b></b>, без markdown ** **):\n\n"
    "⭐ <b>Оценка:</b> N/10\n"
    "✅ <b>Сильное:</b> 1 короткий пункт\n"
    "🛠 <b>Улучши так:</b> 1 конкретный совет\n\n"
    "Будь краток (до ~70 слов), мотивируй продолжать каждый день."
)

WHEEL_SYSTEM = (
    "Ты — ведущий розыгрыша в школе нейросетей True AI Academy. Ученик выиграл приз на колесе "
    "удачи. В 1-2 тёплых предложениях на русском поздравь и свяжи приз с его целью. "
    "Только HTML <b></b>, без markdown. Без выдуманных фактов о человеке."
)


# ─── VISION через OpenRouter (для «первого AI-чуда») ────────────────────────────────────────────────
# Бесплатные vision-модели OpenRouter → дешёвый платный резерв. Только OpenRouter, без Google напрямую.
AI_VISION_MODELS = [
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "qwen/qwen2.5-vl-72b-instruct:free",
    "google/gemini-2.0-flash-exp:free",  # это запрос в OpenRouter, не напрямую в Google
]
AI_VISION_PAID = "openai/gpt-4o-mini"

# Модель ГЕНЕРАЦИИ/редактирования изображений через OpenRouter (nano-banana).
# Платная (~$0.04/картинка), поэтому в сценарии «первого чуда» — строго 1 раз на аккаунт.
# Слаги меняются (preview → GA), поэтому перебираем кандидатов; env OPENROUTER_IMAGE_MODEL
# ставится первым, если задан.
_img_env = os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip()
AI_IMAGE_MODELS = ([_img_env] if _img_env else []) + [
    "google/gemini-2.5-flash-image",          # основной: стабильно отдаёт картинку на редактировании фото
    "google/gemini-3.1-flash-image-preview",  # запасной
]

# Системка для превращения «желания» юзера в качественный промпт для image-модели.
WOW_PROMPT_SYSTEM = (
    "Ты — промпт-инженер для нейросети, редактирующей фото. Пользователь прислал фото и написал "
    "своими словами, что хочет с ним сделать. Преврати это в ОДИН чёткий промпт на английском "
    "для image-editing модели. Сохрани узнаваемость лица с фото. Верни ТОЛЬКО сам промпт, "
    "без кавычек и пояснений."
)


async def ai_generate_image(prompt: str, image_b64: str):
    """Редактирует фото по промпту через OpenRouter (nano-banana). Возвращает bytes или None.
    Перебирает кандидатов image-моделей (слаги меняются: preview → GA)."""
    if not OPENROUTER_KEY:
        return None
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    headers.update(OPENROUTER_EXTRA)
    timeout = aiohttp.ClientTimeout(total=120)
    for model in AI_IMAGE_MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "modalities": ["image", "text"],
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(OPENROUTER_URL, json=payload, headers=headers) as r:
                    data = await r.json()
                    if r.status != 200:
                        raise RuntimeError(f"HTTP {r.status}: {str(data)[:200]}")
                    msg = data["choices"][0]["message"]
                    # Картинки приходят в message.images[].image_url.url (data URL)
                    for im in (msg.get("images") or []):
                        url = (im.get("image_url") or {}).get("url", "")
                        if url.startswith("data:"):
                            logging.info(f"image OK via OpenRouter:{model}")
                            return base64.b64decode(url.split(",", 1)[1])
                    logging.warning(f"image model {model} returned no images → next")
        except Exception as e:
            logging.warning(f"ai_generate_image {model} failed: {e} → next")
            continue
    logging.error("ai_generate_image: all image models exhausted")
    return None


async def ai_vision(system: str, user_text: str, image_b64: str, max_tokens: int = 350) -> str:
    """Vision-вызов через OpenRouter: free-модели → дешёвый резерв. None, если недоступно."""
    if not OPENROUTER_KEY:
        return None
    content = [
        {"type": "text", "text": user_text},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    headers.update(OPENROUTER_EXTRA)
    timeout = aiohttp.ClientTimeout(total=45)
    for model in AI_VISION_MODELS + [AI_VISION_PAID]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(OPENROUTER_URL, json=payload, headers=headers) as r:
                    data = await r.json()
                    if r.status != 200:
                        raise RuntimeError(f"HTTP {r.status}: {str(data)[:200]}")
                    out = data["choices"][0]["message"]["content"].strip()
                    if out:
                        logging.info(f"AI vision OK via OpenRouter:{model}")
                        return out
        except Exception as e:
            logging.warning(f"OpenRouter vision {model} failed: {e} → next")
            continue
    logging.error("AI vision: all OpenRouter models exhausted")
    return None


# Готовый пул заданий+промптов (нулевой расход / fallback, если AI недоступен или прислали текст)
WOW_TASKS = [
    {
        "task": "Сфоткай себя, друга или брата по пояс — и пришли фото сюда.",
        "prompt": "professional cinematic portrait, superhero style, dramatic lighting, "
                  "highly detailed, 8k, keep the face identical to the photo",
    },
    {
        "task": "Пришли любое своё фото (или фото друга) — превратим в Pixar-персонажа.",
        "prompt": "3D Pixar / Disney animation style character, cute, big expressive eyes, "
                  "soft studio lighting, keep the face recognizable from the photo",
    },
    {
        "task": "Скинь фото в полный рост или по пояс — сделаем деловой портрет на аватарку.",
        "prompt": "clean professional business headshot, neutral studio background, "
                  "soft lighting, confident look, LinkedIn style, keep the face identical",
    },
]


def wow_task():
    idx = datetime.now().timetuple().tm_yday % len(WOW_TASKS)
    return WOW_TASKS[idx]


def _ensure_game(uid: str):
    u = users.setdefault(uid, {})
    u.setdefault("xp", 0)
    u.setdefault("badges", [])
    u.setdefault("streak", 0)
    u.setdefault("last_day", "")
    return u


def level_for(xp: int):
    name, nxt = LEVELS[0][1], None
    for i, (thr, lbl) in enumerate(LEVELS):
        if xp >= thr:
            name = lbl
            nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return name, nxt


def add_xp(uid: str, reason: str):
    u = _ensure_game(uid)
    amount = XP_RULES.get(reason, 0)
    if amount:
        u["xp"] = u.get("xp", 0) + amount
        save_users()
    return amount


def give_badge(uid: str, badge_id: str) -> bool:
    """Возвращает True, если бейдж выдан впервые."""
    u = _ensure_game(uid)
    if badge_id not in u["badges"]:
        u["badges"].append(badge_id)
        save_users()
        return True
    return False


def touch_streak(uid: str):
    """Обновляет ежедневную серию. Возвращает (streak, новый_бейдж|None)."""
    u = _ensure_game(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    last = u.get("last_day", "")
    if last == today:
        return u["streak"], None
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    u["streak"] = u.get("streak", 0) + 1 if last == yesterday else 1
    u["last_day"] = today
    add_xp(uid, "daily")
    new_badge = None
    if u["streak"] >= 7 and give_badge(uid, "streak7"):
        new_badge = "streak7"
    elif u["streak"] >= 3 and give_badge(uid, "streak3"):
        new_badge = "streak3"
    save_users()
    return u["streak"], new_badge


# ─── RATE-LIMIT: защита от спама AI / абуза механик ────────────────────────────────────────────────
def rate_ok(uid: str, key: str, window: int) -> bool:
    """True, если с прошлого срабатывания key прошло >= window сек. Иначе False (заблокировано)."""
    if is_admin(uid):
        return True  # админ тестирует без задержек
    u = _ensure_game(uid)
    rl = u.setdefault("rl", {})
    last = rl.get(key, 0)
    if now_ts() - last < window:
        return False
    rl[key] = now_ts()
    save_users()
    return True


def rate_left(uid: str, key: str, window: int) -> int:
    """Сколько секунд осталось до разблокировки (0 — можно)."""
    u = _ensure_game(uid)
    last = u.get("rl", {}).get(key, 0)
    left = int(window - (now_ts() - last))
    return max(0, left)


# ─── МЕХАНИКА №6: личная скидка за прогресс (endowed progress + loss aversion) ──────────────────────
def unlocked_discount(uid: str) -> int:
    """Размер скидки (₽), заслуженной по текущему XP. Чисто по порогам, без срока."""
    u = _ensure_game(uid)
    xp = u.get("xp", 0)
    disc = 0
    for thr, amount in DISCOUNT_TIERS:
        if xp >= thr:
            disc = amount
    return disc


def refresh_discount(uid: str) -> int:
    """Фиксирует разблокированную скидку и продлевает срок её жизни. Возвращает активную скидку (₽)."""
    u = _ensure_game(uid)
    disc = unlocked_discount(uid)
    if disc > 0:
        prev = u.get("discount", 0)
        # Продлеваем дедлайн, если скидка выросла или истекла
        if disc > prev or now_ts() > u.get("discount_until", 0):
            u["discount_until"] = now_ts() + DISCOUNT_TTL
        u["discount"] = disc
        save_users()
    return disc


def active_discount(uid: str) -> int:
    """Активная (не сгоревшая) скидка в ₽ — 0, если истекла или не заслужена."""
    u = _ensure_game(uid)
    disc = min(u.get("discount", 0), unlocked_discount(uid))
    if disc <= 0:
        return 0
    if now_ts() > u.get("discount_until", 0):
        return 0
    return disc


def discount_deadline(uid: str) -> str:
    u = _ensure_game(uid)
    until = u.get("discount_until", 0)
    if until <= now_ts():
        return ""
    return datetime.fromtimestamp(until).strftime("%H:%M %d.%m")


def price_with_discount(uid: str, plan_key: str) -> tuple:
    """(базовая_акция, финальная_цена_со_скидкой, скидка_₽). Не опускаем ниже 990 ₽."""
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    base = t["now"]
    disc = active_discount(uid)
    final = max(990, base - disc)
    return base, final, base - final


# ─── МЕХАНИКА №7: колесо удачи (variable reward + reciprocity) ─────────────────────────────────────
# Каждый приз — повод оплатить СЕГОДНЯ. type: discount даёт доп. скидку поверх скидки за прогресс.
WHEEL_PRIZES = [
    {"id": "disc1000", "label": "💸 Доп. скидка 1 000 ₽", "type": "discount", "value": 1000},
    {"id": "disc1500", "label": "💸 Доп. скидка 1 500 ₽", "type": "discount", "value": 1500},
    {"id": "prompts",  "label": "🎁 100+ продающих промптов", "type": "bonus", "value": 0},
    {"id": "guide",    "label": "📘 Гайд «30 источников заказов»", "type": "bonus", "value": 0},
    {"id": "vipmonth", "label": "👑 Месяц VIP-куратора бесплатно", "type": "bonus", "value": 0},
    {"id": "disc500",  "label": "💸 Доп. скидка 500 ₽", "type": "discount", "value": 500},
]


def spin_wheel(uid: str) -> dict:
    """Крутит колесо один раз за всё время. Возвращает приз или None, если уже крутил."""
    u = _ensure_game(uid)
    if u.get("wheel"):
        return None
    prize = random.choice(WHEEL_PRIZES)
    u["wheel"] = prize["id"]
    u["wheel_at"] = now_ts()
    if prize["type"] == "discount":
        # Доп. скидка поверх прогресс-скидки, со своим суточным дедлайном
        u["wheel_discount"] = prize["value"]
        u["wheel_until"] = now_ts() + 24 * 3600
    save_users()
    return prize


def wheel_discount_active(uid: str) -> int:
    u = _ensure_game(uid)
    if now_ts() > u.get("wheel_until", 0):
        return 0
    return u.get("wheel_discount", 0)


# ─── МАГАЗИН ЗА XP: тратим опыт на генерации и скидки на курс ───────────────────────────────────────
# id: (название, цена в XP, тип, значение). type: "gen" даёт N генераций, "disc" — скидку в ₽.
SHOP_ITEMS = [
    ("gen3",   "🎨 3 AI-генерации фото",   120, "gen", 3),
    ("gen5",   "🎨 5 AI-генераций фото",   180, "gen", 5),
    ("gen10",  "🎨 10 AI-генераций фото",  300, "gen", 10),
    ("disc500",  "💸 Скидка 500 ₽ на курс",  150, "disc", 500),
    ("disc1000", "💸 Скидка 1 000 ₽ на курс", 280, "disc", 1000),
    ("disc2000", "💸 Скидка 2 000 ₽ на курс", 500, "disc", 2000),
]
SHOP_BY_ID = {i[0]: i for i in SHOP_ITEMS}


def spend_xp(uid: str, cost: int) -> bool:
    """Списывает XP, если хватает. True — успешно."""
    u = _ensure_game(uid)
    if u.get("xp", 0) < cost:
        return False
    u["xp"] = u.get("xp", 0) - cost
    save_users()
    return True


def gen_credits(uid: str) -> int:
    return _ensure_game(uid).get("gen_credits", 0)


def add_gen_credits(uid: str, n: int):
    u = _ensure_game(uid)
    u["gen_credits"] = u.get("gen_credits", 0) + n
    save_users()


def use_gen_credit(uid: str) -> bool:
    u = _ensure_game(uid)
    if u.get("gen_credits", 0) <= 0:
        return False
    u["gen_credits"] -= 1
    save_users()
    return True


def shop_discount(uid: str) -> int:
    """Постоянная скидка ₽, купленная за XP в магазине."""
    return _ensure_game(uid).get("shop_discount", 0)


def total_discount(uid: str) -> int:
    """Личная скидка ₽ — БЕРЁМ МАКСИМАЛЬНУЮ из источников (прогресс / колесо / магазин),
    а НЕ сумму. Складывание трёх скидок раньше обрушивало цену в пол и стирало
    разницу между тарифами (VIP = Базовый). Теперь действует одна — самая выгодная."""
    return max(active_discount(uid), wheel_discount_active(uid), shop_discount(uid))


def final_price(uid: str, plan_key: str) -> int:
    """Финальная цена тарифа ₽ с учётом личной скидки, но не ниже «пола» тарифа —
    чтобы тарифы не схлопывались в одну сумму."""
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    refresh_discount(uid)
    floor = t.get("floor", max(990, int(t["now"] * 0.6)))
    return max(floor, t["now"] - total_discount(uid))


# ─── КУРС: последовательная выдача дней (3–8 — после оплаты) ────────────────────────────────────
# Правила: дни 1–2 — бесплатно. Дни 3–8 — купившим курс. Каждый следующий день
# открывается после отметки «домашка сделана» и не ранее 4 ч с открытия предыдущего.
# День 8 (продвижение/SMM) входит в PRO, иначе докупается за 1 790 ₽.

def is_buyer(uid: str) -> bool:
    u = users.get(uid, {})
    return u.get("stage") == "paid" or "buyer" in _ensure_game(uid).get("badges", []) \
        or u.get("plan", "") in ("base", "vip", "pro")


def user_plan(uid: str) -> str:
    return users.get(uid, {}).get("plan", "")


def has_day8(uid: str) -> bool:
    """8-й день: входит в PRO, либо докуплен отдельно."""
    return user_plan(uid) == "pro" or _ensure_game(uid).get("day8", False)


def _days(uid: str) -> dict:
    return _ensure_game(uid).setdefault("days", {})


def day_open_at(uid: str, n: int) -> float:
    return _days(uid).get(str(n), {}).get("open", 0)


def mark_day_open(uid: str, n: int):
    _days(uid).setdefault(str(n), {})["open"] = now_ts()
    save_users()


def hw_done(uid: str, n: int) -> bool:
    return _days(uid).get(str(n), {}).get("hw", False)


def mark_hw(uid: str, n: int):
    _days(uid).setdefault(str(n), {})["hw"] = True
    save_users()


def course_gate(uid: str, n: int):
    """Возвращает (status, wait_left_сек). status: ok / pay / day8pay / hw / wait."""
    if is_admin(uid):
        return "ok", 0  # админ открывает любой день для теста
    if not is_buyer(uid):
        return "pay", 0
    if n == 8 and not has_day8(uid):
        return "day8pay", 0
    if n <= 3:
        return "ok", 0
    prev = n - 1
    if not hw_done(uid, prev):
        return "hw", 0
    left = HW_COOLDOWN - (now_ts() - day_open_at(uid, prev))
    if left > 0:
        return "wait", int(left)
    return "ok", 0


def course_target(uid: str):
    """Следующий день для прохождения (3..8) или None, если курс пройден."""
    opened = [n for n in range(3, TOTAL_DAYS + 1) if day_open_at(uid, n) > 0]
    if not opened:
        return 3
    last = max(opened)
    return last + 1 if last < TOTAL_DAYS else None


def _human_left(left: int) -> str:
    return f"~{int((left + 3599) // 3600)} ч" if left >= 3600 else f"~{max(1, int((left + 59) // 60))} мин"


def course_hub_kb(uid: str):
    rows = []
    if is_buyer(uid):
        target = course_target(uid)
        if target is None:
            rows.append([InlineKeyboardButton(text="🔁 Повторить уроки", callback_data="day_3")])
        else:
            st, _ = course_gate(uid, target)
            label = f"📖 Открыть день {target}" if st == "ok" else f"🎓 День {target}"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"day_{target}")])
    else:
        rows.append([InlineKeyboardButton(text="💰 Тарифы", callback_data="tariffs")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lesson_kb(n: int):
    rows = [[InlineKeyboardButton(text=f"📖 Открыть урок {n}", url=COURSE_LINKS[n])]]
    if n < TOTAL_DAYS:
        rows.append([InlineKeyboardButton(text="✅ Я выполнил домашнее задание", callback_data=f"hw_{n}")])
    rows.append([InlineKeyboardButton(text="📚 Мои уроки", callback_data="course")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def day8_offer_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть 8-й день — 1 790 ₽", callback_data="buy_day8")],
        [InlineKeyboardButton(text="📚 Мои уроки", callback_data="course")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


# ─── МЕХАНИКА №1: челлендж дня (тема ротируется по дате — без затрат на AI) ─────────────────────────
CHALLENGE_THEMES = [
    "Промпт для рекламного фото товара (например, кроссовки на ярком фоне)",
    "Промпт для логотипа кофейни в минималистичном стиле",
    "Промпт для обложки YouTube-ролика про заработок",
    "Промпт для карточки товара на маркетплейс (Wildberries/Ozon)",
    "Промпт для аватарки в деловом стиле для соцсетей",
    "Промпт для рекламного баннера распродажи",
    "Промпт для иллюстрации к посту в Telegram-канал",
]


def challenge_theme() -> str:
    idx = datetime.now().timetuple().tm_yday % len(CHALLENGE_THEMES)
    return CHALLENGE_THEMES[idx]


def progress_bar(xp: int, nxt) -> str:
    if not nxt:
        return "██████████ MAX"
    cur_thr = 0
    for thr, _ in LEVELS:
        if xp >= thr:
            cur_thr = thr
    span = nxt[0] - cur_thr
    filled = int(round(10 * (xp - cur_thr) / span)) if span else 10
    filled = max(0, min(10, filled))
    return "█" * filled + "░" * (10 - filled)


def profile_text(uid: str, name: str) -> str:
    u = _ensure_game(uid)
    xp = u.get("xp", 0)
    lvl, nxt = level_for(xp)
    bar = progress_bar(xp, nxt)
    nxt_line = f"До «{nxt[1]}»: {nxt[0] - xp} XP" if nxt else "Максимальный уровень 👑"
    badges = u.get("badges", [])
    badges_str = "  ".join(BADGES[b] for b in badges if b in BADGES) or "— пока нет, всё впереди!"

    # Механика №6: личная скидка за прогресс
    refresh_discount(uid)
    disc = active_discount(uid)
    nxt_disc = next(((thr, amt) for thr, amt in DISCOUNT_TIERS if xp < thr), None)
    if disc > 0:
        dl = discount_deadline(uid)
        disc_block = (
            f"💸 <b>Твоя личная скидка: {disc} ₽</b>\n"
            f"⏳ Сгорит: <b>{dl}</b> — успей применить на тарифе!\n"
        )
        if nxt_disc:
            disc_block += f"📈 До скидки {nxt_disc[1]} ₽ осталось {nxt_disc[0] - xp} XP\n"
        disc_block += "\n"
    elif nxt_disc:
        disc_block = (
            f"💸 <b>Накопи XP — открой скидку!</b>\n"
            f"До скидки {nxt_disc[1]} ₽ осталось <b>{nxt_disc[0] - xp} XP</b>\n\n"
        )
    else:
        disc_block = ""

    credits = gen_credits(uid)
    credits_line = f"🎨 Доступно генераций: <b>{credits}</b>\n" if credits else ""
    shop_disc = shop_discount(uid)
    shop_line = f"🛒 Скидка из магазина: <b>{shop_disc} ₽</b>\n" if shop_disc else ""

    return (
        f"🎮 <b>Профиль: {name}</b>\n\n"
        f"Уровень: <b>{lvl}</b>\n"
        f"Опыт: <b>{xp} XP</b>\n"
        f"{bar}\n"
        f"{nxt_line}\n\n"
        f"🔥 Серия дней подряд: <b>{u.get('streak', 0)}</b>\n"
        f"{credits_line}{shop_line}\n"
        f"{disc_block}"
        f"🏅 <b>Достижения ({len(badges)}/{len(BADGES)}):</b>\n{badges_str}\n\n"
        "💡 Меняй XP в 🛒 магазине на генерации и скидки. "
        "Каждый день: челлендж + урок = XP. Топ-3 недели получают бонусы."
    )


def leaderboard_text() -> str:
    ranked = sorted(
        ((u.get("xp", 0), u.get("name", "Аноним")) for u in users.values()),
        key=lambda x: x[0], reverse=True,
    )
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    rows = []
    for i, (xp, nm) in enumerate(ranked[:10]):
        if xp <= 0:
            continue
        rows.append(f"{medals[i]} <b>{nm}</b> — {xp} XP")
    body = "\n".join(rows) or "Пока никто не набрал XP. Будь первым! 🚀"
    return (
        "🏆 <b>РЕЙТИНГ УЧЕНИКОВ НЕДЕЛИ</b>\n\n"
        f"{body}\n\n"
        "🎁 <b>ПРИЗЫ В КОНЦЕ НЕДЕЛИ:</b>\n"
        "🥇 1 место — VIP-доступ бесплатно\n"
        "🥈 2 место — скидка 2 000 ₽\n"
        "🥉 3 место — гайд «30 источников заказов»\n\n"
        "💡 XP даётся за челлендж дня, уроки и серии. "
        "Пройди челлендж сегодня — и обгони соседей по таблице!"
    )


def my_rank(uid: str) -> tuple:
    """(позиция, xp) текущего юзера в рейтинге; позиция с 1."""
    ranked = sorted(
        ((u_id, u.get("xp", 0)) for u_id, u in users.items()),
        key=lambda x: x[1], reverse=True,
    )
    for i, (u_id, xp) in enumerate(ranked, 1):
        if u_id == uid:
            return i, xp
    return len(ranked) + 1, 0


def badge_toast(badge_id: str) -> str:
    return f"\n\n🎉 <b>Новое достижение:</b> {BADGES.get(badge_id, badge_id)}  (+бейдж в профиль)"


class BroadcastState(StatesGroup):
    waiting = State()


class ChallengeState(StatesGroup):
    waiting = State()


class WowState(StatesGroup):
    waiting_photo = State()
    waiting_wish = State()


class GenState(StatesGroup):
    waiting_photo = State()
    waiting_wish = State()


class PayState(StatesGroup):
    waiting_email = State()  # ввод email для чека перед оплатой через API ЮKassa


# ─── КЛАВИАТУРЫ ─────────────────────────────────────────────────────────────────────────────────

def goal_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Хочу зарабатывать удалённо", callback_data="goal_freelance")],
        [InlineKeyboardButton(text="🏢 Хочу прокачать свой бизнес", callback_data="goal_business")],
        [InlineKeyboardButton(text="🔍 Хочу разобраться что такое AI", callback_data="goal_curious")],
    ])


def start_kb(uid: str = None):
    # Главный экран: ключевые действия + геймификация сразу на виду.
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Оживить своё фото (бесплатно)", callback_data="wow")],
        [InlineKeyboardButton(text="🎓 Начать бесплатно — 2 дня курса", callback_data="day1")],
        [InlineKeyboardButton(text="🎁 100+ нейросетей в подарок", callback_data="free_gift")],
        [
            InlineKeyboardButton(text="💰 Тарифы", callback_data="tariffs"),
            InlineKeyboardButton(text="🏆 Отзывы", callback_data="results"),
        ],
        [
            InlineKeyboardButton(text="📚 Мои уроки", callback_data="course"),
            InlineKeyboardButton(text="👤 Кто ведёт курс", callback_data="author"),
        ],
        [InlineKeyboardButton(text="🥊 Челлендж дня (+10 XP)", callback_data="challenge")],
        [
            InlineKeyboardButton(text="🎮 Мой прогресс", callback_data="profile"),
            InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard"),
        ],
        [InlineKeyboardButton(text="🛒 Магазин: обменять опыт на бонусы", callback_data="shop")],
        [InlineKeyboardButton(text="🤝 Позвать друга — 30% тебе", callback_data="referral")],
    ])


def free_gift_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 ЗАБРАТЬ БЕСПЛАТНО ПРЯМО СЕЙЧАС", url=GIFT_LINK)],
        [InlineKeyboardButton(text="🎓 И попробовать курс (2 дня бесплатно)", callback_data="day1")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def day1_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть 1-й день прямо сейчас", url=TRIAL_DAY_1)],
        [InlineKeyboardButton(text="✅ Прошёл 1-й день →", callback_data="day2")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def day2_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Открыть 2-й день", url=TRIAL_DAY_2)],
        [InlineKeyboardButton(text="✅ Готово — крутить КОЛЕСО УДАЧИ 🎰", callback_data="wheel")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def wheel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 КРУТИТЬ КОЛЕСО", callback_data="wheel_spin")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def tariffs_kb(spots: int = None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ VIP — 4 970 ₽  (берут 7 из 10) 🔥", callback_data="buy_vip")],
        [InlineKeyboardButton(text="🚀 PRO + продвижение — 7 970 ₽", callback_data="buy_pro")],
        [InlineKeyboardButton(text="📦 Базовый — 2 970 ₽", callback_data="buy_base")],
        [
            InlineKeyboardButton(text="🛡 Без риска", callback_data="guarantee"),
            InlineKeyboardButton(text="❓ Вопросы", callback_data="faq"),
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def pay_choice_kb(plan_key: str):
    """Оплата через ЮKassa: API (СБП/T-Pay/SberPay/карта) → Telegram-карта → менеджер."""
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    rows = []
    if YOOKASSA_API_ENABLED:
        label = f"💳 Оплатить {t['now']:,} ₽ — СБП · T-Pay · SberPay · карта".replace(",", " ")
        if YOOKASSA_API_TEST:
            label += "  (ТЕСТ)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"ykapi_{plan_key}")])
    elif YOOKASSA_TOKEN:
        label = f"💳 Оплатить картой — {t['now']:,} ₽".replace(",", " ")
        if YOOKASSA_TEST:
            label += "  (ТЕСТ)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"yk_{plan_key}")])
    else:
        rows.append([InlineKeyboardButton(text="💳 Картой РФ через менеджера",
                                          callback_data=f"card_{plan_key}")])
    if plan_key not in ("test", "day8"):
        rows.append([InlineKeyboardButton(text="➕ Добавить созвон с куратором +990 ₽",
                                          callback_data=f"bump_{plan_key}")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def to_manager_with_bump_kb(plan: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить личный созвон с куратором +990 ₽", callback_data=f"bump_{plan}")],
        [InlineKeyboardButton(text="💬 Написать менеджеру — оплата за 2 минуты", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def to_manager_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру — ответ за 5 минут", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def downsell_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Ок, беру VIP — 4 970 ₽", callback_data="buy_vip")],
        [InlineKeyboardButton(text="📦 А это Базовый хватит? — 2 970 ₽", callback_data="buy_base")],
        [InlineKeyboardButton(text="⏰ Подумать — напомни через день", callback_data="remind_24h")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


# ─── ВСПОМОГАТЕЛЬНАЯ ───────────────────────────────────────────────────────────────────

async def show(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup):
    # Сразу подтверждаем callback, пока он не протух (иначе "query is too old")
    try:
        await call.answer()
    except Exception:
        pass
    try:
        await call.message.delete()
    except Exception:
        pass
    try:
        await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"show() answer failed: {e}")


async def show_img(call: CallbackQuery, img_name: str, text: str, kb: InlineKeyboardMarkup):
    """Как show(), но с брендовой шапкой-картинкой (фото + подпись).
    Безопасно деградирует к тексту, если картинки нет, подпись длиннее лимита
    Telegram (1024) или отправка фото не удалась."""
    try:
        await call.answer()
    except Exception:
        pass
    try:
        await call.message.delete()
    except Exception:
        pass
    path = os.path.join(IMG_DIR, img_name)
    if os.path.exists(path) and len(text) <= 1024:
        try:
            await call.message.answer_photo(
                photo=FSInputFile(path), caption=text, reply_markup=kb)
            return
        except Exception as e:
            logging.warning(f"show_img() photo failed: {e} → text fallback")
    try:
        await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"show_img() answer failed: {e}")


# ─── ХЭНДЛЕРЫ ──────────────────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    name = message.from_user.first_name or "друг"

    is_new = user_id not in users
    if is_new:
        users[user_id] = {"name": name, "stage": "start", "start_at": now_ts()}
        save_users()
        uname = f"@{message.from_user.username}" if message.from_user.username else "нет username"
        # Ссылки для открытия профиля: по username (если есть) и по ID (tg://user)
        open_link = (
            f"https://t.me/{message.from_user.username}" if message.from_user.username
            else f"tg://user?id={user_id}"
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 <b>Новый пользователь!</b>\n\n"
                f"👤 {name} ({uname})\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"👥 Всего в боте: {len(users)}\n\n"
                f"➡️ <a href=\"{open_link}\">Открыть профиль</a>",
                disable_web_page_preview=True,
            )
        except Exception:
            pass

    # Источник перехода (?start=land с сайта и т.п.) + ежедневная серия
    payload = ""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        # Санитайз: только буквы/цифры/_/-, максимум 32 символа — иначе раздувание счётчиков
        raw = parts[1].strip()
        payload = "".join(c for c in raw if c.isalnum() or c in "_-")[:32]
    track("start_" + (payload or "direct"), user_id)
    touch_streak(user_id)
    if user_id in users:
        users[user_id]["seen_at"] = now_ts()
        # Сброс флага реактивации — чтобы при новой паузе снова смогли напомнить
        users[user_id].pop("fu_reengage", None)
        save_users()

    text = (
        f"👋 <b>{name}, рад видеть!</b>\n\n"
        "Помогу разобраться с нейросетями с нуля —\n"
        "спокойно и по шагам. Будет даже интересно:\n"
        "проходишь уроки, копишь опыт, открываешь награды.\n\n"
        "🎁 Первые 2 дня — бесплатно, без карты\n"
        "🎮 За каждый шаг — опыт и небольшие бонусы\n"
        "💬 Застрянешь — помогу\n\n"
        "С чего начнём? Выбери, что тебе ближе 👇"
    )

    # Приветственное фото — только новым пользователям.
    if is_new and os.path.exists(WELCOME_IMG):
        try:
            await message.answer_photo(
                photo=FSInputFile(WELCOME_IMG),
                caption=text,
                reply_markup=goal_kb()
            )
            return
        except Exception as e:
            logging.warning(f"welcome photo failed: {e}")
    elif is_new:
        logging.warning(f"welcome photo not found at {WELCOME_IMG}")
    await message.answer(text, reply_markup=goal_kb())


@dp.callback_query(lambda c: c.data.startswith("goal_"))
async def cb_goal(call: CallbackQuery):
    goal = call.data.replace("goal_", "")
    user_id = str(call.from_user.id)
    if user_id in users:
        users[user_id]["goal"] = goal
        save_users()

    hook = GOAL_HOOKS.get(goal, "")
    text = (
        hook +
        "✨ <b>Проще один раз увидеть.</b>\n"
        "Пришли любое фото — и нейросеть его оживит\n"
        "за минуту. Бесплатно, сам убедишься, что это легко.\n\n"
        "🎓 А дальше — 2 дня курса бесплатно\n"
        "или 100+ нейросетей в подарок.\n\n"
        "Что выберешь? 👇"
    )
    await show(call, text, start_kb())


@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    name = call.from_user.first_name or "друг"
    text = (
        f"🏠 <b>Главное меню</b>\n\n"
        f"{social_proof()}\n\n"
        f"{name}, что выбираешь? 👇"
    )
    await show(call, text, start_kb())


@dp.callback_query(lambda c: c.data == "free_gift")
async def cb_free_gift(call: CallbackQuery):
    user_id = str(call.from_user.id)
    track("free_gift", user_id)
    add_xp(user_id, "free_gift")
    give_badge(user_id, "explorer")
    text = (
        "🎁 <b>100+ нейросетей — в подарок</b>\n\n"
        "Целый набор: рисуют картинки, монтируют видео,\n"
        "пишут тексты, делают музыку и озвучку.\n\n"
        "🎨 Midjourney · 🎬 Kling, Runway · 🤖 ChatGPT\n"
        "🎵 Suno · 🔊 ElevenLabs и ещё под сотню\n\n"
        "Бесплатно и без карты — просто чтобы ты попробовал.\n"
        f"Уже забрали больше {STUDENTS_COUNT} человек.\n\n"
        "👇 Забрать:"
    )
    await show_img(call, "gift.jpg", text, free_gift_kb())


@dp.callback_query(lambda c: c.data == "day1")
async def cb_day1(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "day1")
    track("day1", user_id)
    mark_day_open(user_id, 1)
    add_xp(user_id, "day1")
    new_badge = give_badge(user_id, "first_step")
    bonus = badge_toast("first_step") if new_badge else ""

    text = (
        "🎓 <b>День 1 — первые гиперреалистичные фото</b>  <i>(+10 XP)</i>\n"
        "█░░ 33%\n\n"
        "Никакой скучной теории — сразу практика.\n\n"
        "<b>За ближайший час ты:</b>\n"
        "▸ запустишь Nano Banana 2 и GPT Image 2\n"
        "▸ сделаешь первые гиперреалистичные фото\n"
        "▸ напишешь свой первый рабочий промпт\n"
        "▸ поймёшь, как это превратить в доход\n\n"
        "А после 2-го дня будет небольшой сюрприз 🙂\n\n"
        "👇 Открыть первый день:"
        + bonus
    )
    await show_img(call, "day1.jpg", text, day1_kb())


@dp.callback_query(lambda c: c.data == "day2")
async def cb_day2(call: CallbackQuery):
    user_id = str(call.from_user.id)

    # ─── Гейт: 2-й день открывается только через 12 ч после старта 1-го ───
    # (админ тестирует без задержки)
    day1_at = users.get(user_id, {}).get("day1_at")
    if not is_admin(user_id) and not day1_at:
        await show_img(
            call, "day1.jpg",
            "🔒 <b>Сначала — первый день</b>\n\n"
            "2-й урок открывается уже после первого.\n"
            "Начни с него — это бесплатно 👇",
            day1_kb(),
        )
        return
    left = 0 if is_admin(user_id) else DAY2_COOLDOWN - (now_ts() - (day1_at or now_ts()))
    if left > 0:
        when = f"~{int((left + 3599) // 3600)} ч" if left >= 3600 else f"~{max(1, int((left + 59) // 60))} мин"
        unlock = datetime.fromtimestamp(day1_at + DAY2_COOLDOWN).strftime("%H:%M %d.%m")
        await show(
            call,
            "🔒 <b>2-й день откроется чуть позже</b>\n\n"
            "Я специально сделал паузу: дай материалу\n"
            "первого дня улечься — так усвоится в разы лучше.\n\n"
            f"⏳ Откроется через <b>{when}</b> (в {unlock}).\n"
            "Я напомню сам, как будет готово 🙂\n\n"
            "А пока можно не скучать 👇",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✨ Оживить своё фото (бесплатно)", callback_data="wow")],
                [InlineKeyboardButton(text="🥊 Челлендж дня (+10 XP)", callback_data="challenge")],
                [InlineKeyboardButton(text="🎁 100+ нейросетей в подарок", callback_data="free_gift")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
        )
        return

    set_stage(user_id, "day2")
    track("day2", user_id)
    add_xp(user_id, "day2")
    new_badge = give_badge(user_id, "day1_done")
    bonus = badge_toast("day1_done") if new_badge else ""

    text = (
        "🔥 <b>День 2 — промпты и GPT Image 2</b>  <i>(+15 XP)</i>\n"
        "██░ 66%\n\n"
        "Первый день позади! Сегодня — самое полезное:\n"
        "как писать промпты, чтобы нейросеть выдавала\n"
        "именно то, что ты задумал.\n\n"
        "<b>Внутри:</b>\n"
        "▸ формула рабочего промпта\n"
        "▸ возможности GPT Image 2 на практике\n\n"
        "А в конце — небольшой подарок для тех, кто дошёл 🙂\n\n"
        "👇 Открыть второй день:"
        + bonus
    )
    mark_day_open(user_id, 2)
    await show_img(call, "day2.jpg", text, day2_kb())


# ─── КУРС: дни 3–8 (после оплаты), домашка → +4 ч → следующий день ──────────────────────────────

@dp.callback_query(lambda c: c.data == "course")
async def cb_course(call: CallbackQuery):
    user_id = str(call.from_user.id)
    track("course_open", user_id)
    if not is_buyer(user_id):
        await show(
            call,
            "📚 <b>Уроки курса</b>\n\n"
            "Дни 1–2 — бесплатно, попробуй прямо из меню.\n"
            "Дни 3–8 открываются после оплаты, по одному:\n"
            "сделал домашку → через 4 часа следующий день.\n\n"
            "Так материал реально усваивается, а не забывается 🙂\n\n"
            "👇 Посмотреть тарифы:",
            tariffs_kb(get_spots()),
        )
        return
    target = course_target(user_id)
    opened = [n for n in range(3, TOTAL_DAYS + 1) if day_open_at(user_id, n) > 0]
    progress = max(opened) if opened else 2
    bar = "▰" * progress + "▱" * (TOTAL_DAYS - progress)
    if target is None:
        body = "🎉 Ты прошёл все 8 дней. Красавчик!\nТеперь — практика и первые заказы 🚀"
    else:
        st, left = course_gate(user_id, target)
        if st == "ok":
            body = f"Следующий — <b>день {target}</b>. Можно открывать 👇"
        elif st == "wait":
            body = f"<b>День {target}</b> откроется через {_human_left(left)}. Пусть уляжется 🙂"
        elif st == "hw":
            body = f"Отметь домашку дня {target - 1} — и откроется день {target}."
        elif st == "day8pay":
            body = ("<b>День 8</b> — бонусный: SMM, продвижение, продажи и фриланс.\n"
                    "Он не входит в твой тариф, открывается отдельно за 1 790 ₽.")
        else:
            body = f"Продолжаем с дня {target}."
    text = f"📚 <b>Твой курс — {progress}/{TOTAL_DAYS}</b>\n{bar}\n\n{body}"
    kb = day8_offer_kb() if (target == 8 and not has_day8(user_id)) else course_hub_kb(user_id)
    await show(call, text, kb)


@dp.callback_query(lambda c: c.data.startswith("day_"))
async def cb_course_day(call: CallbackQuery):
    user_id = str(call.from_user.id)
    try:
        n = int(call.data.replace("day_", ""))
    except ValueError:
        await call.answer()
        return
    if n not in COURSE_LINKS or n < 3:
        await call.answer()
        return

    status, left = course_gate(user_id, n)
    if status == "pay":
        await show(
            call,
            "🔒 <b>Это уроки курса</b>\n\n"
            "Дни 3–8 открываются после оплаты. Первые 2 дня\n"
            "ты уже прошёл бесплатно — глянь тарифы, там всё нужное 👇",
            tariffs_kb(get_spots()),
        )
        return
    if status == "day8pay":
        await show(
            call,
            "🚀 <b>День 8 — продвижение и продажи</b>\n\n"
            "Финальный бонус-день: SMM, продвижение, продажи,\n"
            "маркетинг и фриланс — как превратить навык в поток заказов.\n\n"
            "Он не входит в Базовый и VIP — открывается отдельно\n"
            "за <b>1 790 ₽</b> (а в тарифе PRO уже включён).\n\n"
            "👇 Открыть 8-й день:",
            day8_offer_kb(),
        )
        return
    if status == "hw":
        await show(
            call,
            f"📝 <b>Сначала — домашка дня {n - 1}</b>\n\n"
            f"Открой день {n - 1}, выполни задание и нажми\n"
            "«✅ Я выполнил домашнее задание» — тогда откроется следующий.",
            course_hub_kb(user_id),
        )
        return
    if status == "wait":
        unlock = datetime.fromtimestamp(day_open_at(user_id, n - 1) + HW_COOLDOWN).strftime("%H:%M %d.%m")
        await show(
            call,
            f"⏳ <b>День {n} откроется через {_human_left(left)}</b> (в {unlock})\n\n"
            "Пусть материал предыдущего дня уляжется —\n"
            "так усвоится лучше. Я напомню, как откроется 🙂",
            course_hub_kb(user_id),
        )
        return

    # ok → открываем урок
    mark_day_open(user_id, n)
    track(f"day{n}", user_id)
    title = DAY_TITLES.get(n, "")
    head = f"🎓 <b>День {n} из {TOTAL_DAYS}" + (f" — {title}" if title else "") + "</b>"
    bar = "▰" * n + "▱" * (TOTAL_DAYS - n)
    if n < TOTAL_DAYS:
        tail = (f"Открывай урок и выполни задание в конце.\n"
                f"Как сделаешь — жми «выполнил домашку», и через 4 часа\n"
                f"откроется день {n + 1}.")
    else:
        tail = "Это финальный день курса 🏁\nДальше — практика, портфолио и первые заказы 🚀"
    await show_img(call, f"day{n}.jpg", f"{head}\n{bar}\n\n{tail}\n\n👇", lesson_kb(n))


@dp.callback_query(lambda c: c.data.startswith("hw_"))
async def cb_homework(call: CallbackQuery):
    user_id = str(call.from_user.id)
    try:
        n = int(call.data.replace("hw_", ""))
    except ValueError:
        await call.answer()
        return
    if n not in COURSE_LINKS:
        await call.answer()
        return
    mark_hw(user_id, n)
    track(f"hw_{n}", user_id)
    nxt = n + 1
    if nxt > TOTAL_DAYS:
        await show(call, "🎉 <b>Поздравляю — это была последняя домашка!</b>\nТы прошёл весь курс 🚀", course_hub_kb(user_id))
        return
    left = HW_COOLDOWN - (now_ts() - day_open_at(user_id, n))
    if left <= 0:
        await show(
            call,
            f"🔥 <b>Отлично, домашка засчитана!</b>\nДень {nxt} уже открыт — продолжаем 👇",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📖 Открыть день {nxt}", callback_data=f"day_{nxt}")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
        )
    else:
        unlock = datetime.fromtimestamp(day_open_at(user_id, n) + HW_COOLDOWN).strftime("%H:%M %d.%m")
        await show(
            call,
            f"✅ <b>Принял, домашка дня {n} засчитана!</b>\n\n"
            f"День {nxt} откроется через <b>{_human_left(left)}</b> (в {unlock}).\n"
            "Небольшая пауза — чтобы всё уложилось. Напомню, как откроется 🙂",
            course_hub_kb(user_id),
        )


@dp.callback_query(lambda c: c.data == "special_tariffs")
async def cb_special_tariffs(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "tariffs")
    track("special_tariffs", user_id)
    add_xp(user_id, "tariffs")
    give_badge(user_id, "day2_done")
    tick_spots()
    s = get_spots()

    if user_id in users:
        users[user_id]["offer_expires_at"] = now_ts() + 24 * 3600
        save_users()

    deadline = (datetime.now() + timedelta(hours=24)).strftime("%H:%M %d.%m")

    # Личная скидка (максимальная из источников) с учётом пола тарифа
    refresh_discount(user_id)
    base_vip = TARIFFS["vip"]["now"]
    final_vip = final_price(user_id, "vip")
    real_disc = base_vip - final_vip
    if real_disc > 0:
        disc_block = (
            f"🎯 <b>ТВОЯ ЛИЧНАЯ СКИДКА: −{real_disc} ₽</b>\n"
            f"VIP для тебя: <s>{base_vip} ₽</s> → <b>{final_vip} ₽</b>\n"
            "⏳ Скидка сгорает вместе с предложением — не упусти!\n\n"
        )
    else:
        disc_block = ""

    text = (
        "💚 <b>Спасибо, что дошёл до конца</b>\n"
        "Так делают немногие — и для тебя есть лучшая цена.\n\n"
        f"⏳ Держится до <b>{deadline}</b> · мест по цене: <b>{s}</b>\n\n"
        f"{disc_block}"
        "⭐ <b>VIP с куратором</b>\n"
        "<s>9 900 ₽</s> → <b>4 970 ₽</b> · один раз, доступ навсегда\n"
        "Все 7 дней + куратор + разбор работ + чат\n\n"
        "🎁 В подарок: гайд «где брать заказы»,\n"
        "100+ промптов и шаблон портфолио\n\n"
        "🛡 Спокойно: 2 дня ты уже прошёл бесплатно,\n"
        "и всё, что сделал, остаётся с тобой.\n\n"
        "👇 Выбирай, что подходит:"
    )
    await show_img(call, "special.jpg", text, tariffs_kb(s))


@dp.callback_query(lambda c: c.data == "tariffs")
async def cb_tariffs(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "tariffs")
    tick_spots()
    s = get_spots()

    text = (
        "💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n"
        f"Осталось мест по этой цене: <b>{s}</b> · доступ навсегда\n\n"
        "⭐ <b>VIP С КУРАТОРОМ</b> — берут 7 из 10\n"
        "<s>9 900 ₽</s> → <b>4 970 ₽</b>\n"
        "Все 7 дней + куратор + разбор работ + чат 24/7\n"
        "🎁 + бонусы на 6 470 ₽ бесплатно\n\n"
        "🚀 <b>PRO + ПРОДВИЖЕНИЕ</b>\n"
        "<s>14 900 ₽</s> → <b>7 970 ₽</b>\n"
        "Всё из VIP + где брать заказы, вирусный контент, реклама, SMM\n\n"
        "📦 <b>БАЗОВЫЙ</b>\n"
        "<s>5 900 ₽</s> → <b>2 970 ₽</b>\n"
        "Все 7 дней курса. Без куратора и бонусов\n\n"
        "🚀 8-й день (продвижение, SMM, продажи, фриланс)\n"
        "входит в PRO, в Базовый и VIP — докупается за 1 790 ₽\n\n"
        "🛡 Без риска: сначала 2 дня бесплатно, потом решаешь.\n\n"
        "👇 Выбери тариф:"
    )
    await show_img(call, "tariffs.jpg", text, tariffs_kb(s))


@dp.callback_query(lambda c: c.data == "results")
async def cb_results(call: CallbackQuery):
    text = (
        "🏆 <b>Отзывы учеников</b>\n\n"
        f"За полгода через академию прошли <b>{STUDENTS_COUNT}+ человек.</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Марина, фрилансер → вышла на 60k/мес:</b>\n"
        "<i>«Взяла первый заказ через 3 дня после курса.\n"
        "8 000 ₽ за логотипы. Курс окупился за день»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Алексей, менеджер → +30k к зарплате:</b>\n"
        "<i>«Не технарь. Оказалось,\n"
        "нейросети проще, чем Excel»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Ирина, из дома → 25–40k/мес:</b>\n"
        "<i>«Нашла 4 заказчика на иллюстрации.\n"
        "Не привязана к офису»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Павел, владелец магазина:</b>\n"
        "<i>«Весь контент делаю сам.\n"
        "Отказался от дизайнера»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎓 <b>Следующий кейс — твой.</b>\n"
        "Начни бесплатно:"
    )
    await show_img(call, "results.jpg", text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Попробовать курс бесплатно (2 дня)", callback_data="day1")],
        [InlineKeyboardButton(text="🔥 Подарок — 100+ нейросетей", callback_data="free_gift")],
        [InlineKeyboardButton(text="💰 Смотреть тарифы", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "author")
async def cb_author(call: CallbackQuery):
    track("author", str(call.from_user.id))
    text = (
        "👋 <b>Привет, я Николай — автор курса.</b>\n\n"
        "Сам начинал с нуля: разобрался в нейросетях,\n"
        "стал на них зарабатывать — и теперь учу этому.\n\n"
        f"📌 {STUDENTS_COUNT} учеников уже начали\n"
        "📌 97% делают первое видео к 7-му дню\n"
        "📌 в курсе 10+ нейросетей — всё на практике\n\n"
        "Объясняю по-человечески: без воды, сложных\n"
        "терминов и обещаний «золотых гор».\n"
        "Застрянешь — помогу лично.\n\n"
        "Загляни на бесплатные 2 дня — просто посмотри,\n"
        "как всё устроено. Платить ничего не нужно 👇"
    )
    await show_img(call, "author_card.jpg", text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Начать бесплатно — 2 дня", callback_data="day1")],
        [InlineKeyboardButton(text="💬 Написать Николаю", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "faq")
async def cb_faq(call: CallbackQuery):
    text = (
        "❓ <b>ЧАСТЫЕ ВОПРОСЫ</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Я не технарь, справлюсь?</b>\n"
        "Да. 78% наших студентов — без IT-фона.\n"
        "Умеешь в смартфон — справишься.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Когда смогу применить навык?</b>\n"
        "Первое портфолио — уже к 3–7 дню курса.\n"
        "Дальше всё зависит от тебя: даём план,\n"
        "где искать заказы и сколько за них брать.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>А вдруг не получится?</b>\n"
        "Сначала 2 дня бесплатно — проверь без оплаты.\n"
        "Поддержка 24/7 поможет, если где-то застрял.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Когда начинается обучение?</b>\n"
        "Сразу после оплаты. Доступ 24/7, в своём темпе.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Сколько времени в день?</b>\n"
        "1–2 часа. Для занятых.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Могу оплатить в рассрочку?</b>\n"
        "Да. Рассрочка 0% на 4 месяца через менеджера.\n\n"
        "Остались вопросы? 👇"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="← К тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "guarantee")
async def cb_guarantee(call: CallbackQuery):
    text = (
        "🛡 <b>ПОЧЕМУ ЭТО БЕЗ РИСКА</b>\n\n"
        "Ты ничего не теряешь, даже если передумаешь:\n\n"
        "▸ Первые <b>2 дня</b> курса — бесплатно, без карты\n"
        "▸ Уже за эти дни делаешь реальный результат\n"
        "▸ Платишь, только если сам решил продолжить\n"
        "▸ Доступ к материалам остаётся у тебя навсегда\n"
        "▸ Поддержка 24/7 — не бросим на полпути\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Сначала результат — потом решение.</b>\n"
        "Поэтому остаются те, кому курс реально зашёл.\n\n"
        "💬 <i>«Попробовала бесплатно, втянулась —\n"
        "и осталась» — Ольга</i>"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Ок, беру VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="👤 Кто ведёт курс", callback_data="author")],
        [InlineKeyboardButton(text="← К тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    plan_key = call.data.replace("buy_", "")
    if plan_key not in TARIFFS:
        plan_key = "vip"
    t = TARIFFS[plan_key]
    user_id = str(call.from_user.id)
    set_stage(user_id, "checkout")
    track(f"buy_{plan_key}", user_id)

    total_disc = total_discount(user_id)
    final = final_price(user_id, plan_key)
    if total_disc > 0 and final < t["now"]:
        price_line = (
            f"<s>{t['old']:,} ₽</s> → <s>{t['now']:,} ₽</s> → <b>{final:,} ₽</b>\n"
            f"🎯 Личная скидка <b>−{t['now'] - final} ₽</b> уже применяется при оплате\n"
        ).replace(",", " ")
        disc_hint = "💡 Скидка спишется автоматически — платишь итоговую сумму.\n"
    else:
        price_line = f"<s>{t['old']:,} ₽</s> → <b>{t['now']:,} ₽</b>\n".replace(",", " ")
        disc_hint = "💡 Есть промокод друга на 500 ₽? Его применит менеджер.\n"

    text = (
        f"✅ <b>Отличный выбор — {t['label']}!</b>\n\n"
        f"{price_line}"
        f"{t['perks']}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💳 <b>Оплата</b> — СБП, T-Pay, SberPay или картой через ЮKassa,\n"
        "доступ открывается сразу после оплаты.\n\n"
        "🛡 Без риска: сначала 2 дня бесплатно, потом решаешь.\n"
        f"{disc_hint}\n"
        "👇"
    )
    await show(call, text, pay_choice_kb(plan_key))


@dp.callback_query(lambda c: c.data.startswith("card_"))
async def cb_card(call: CallbackQuery):
    plan_key = call.data.replace("card_", "")
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    user_id = str(call.from_user.id)
    set_stage(user_id, "purchased")
    track("card_request", user_id, plan_key)

    text = (
        f"💳 <b>Оплата картой РФ — {t['label']}</b>\n\n"
        "🎯 <b>Как это работает:</b>\n"
        "1️⃣ Напиши менеджеру\n"
        "2️⃣ Он пришлёт реквизиты (Сбер / Т-Банк / карта)\n"
        "3️⃣ Оплата за 2 минуты\n"
        "4️⃣ Доступ + бонусы приходят сразу\n\n"
        "💡 Промокод друга → скидка 500 ₽.\n"
        "🛡 Без риска: 2 дня бесплатно перед оплатой.\n\n"
        "👇 Написать менеджеру:"
    )
    await show(call, text, to_manager_with_bump_kb(plan_key))

    name = call.from_user.first_name or "Юзер"
    uname = f"@{call.from_user.username}" if call.from_user.username else "нет username"
    goal = GOAL_LABELS.get(users.get(user_id, {}).get("goal", ""), "—")
    final = final_price(user_id, plan_key)
    real_disc = t["now"] - final
    disc_note = f" (личная скидка −{real_disc} ₽)" if real_disc > 0 else ""
    wheel_prize = _ensure_game(user_id).get("wheel", "")
    prize_note = f"\n🎰 Приз колеса: {wheel_prize}" if wheel_prize else ""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 <b>НОВАЯ ЗАЯВКА (карта)!</b>\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: <code>{call.from_user.id}</code>\n"
            f"📦 Тариф: {t['label']} — <b>{final} ₽</b>{disc_note}\n"
            f"🎯 Цель: {goal}{prize_note}"
        )
    except Exception:
        pass


@dp.callback_query(lambda c: c.data.startswith("yk_"))
async def cb_yookassa(call: CallbackQuery):
    plan_key = call.data.replace("yk_", "")
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    user_id = str(call.from_user.id)
    track("yookassa_invoice", user_id, plan_key)
    await call.answer()

    if not YOOKASSA_TOKEN:
        await call.message.answer(
            "💳 Оплата картой пока настраивается. Напиши менеджеру — оформим вручную:",
            reply_markup=to_manager_kb(),
        )
        return

    # Чек для 54-ФЗ (нужен, если в магазине ЮKassa включена фискализация)
    provider_data = json.dumps({
        "receipt": {
            "tax_system_code": YOOKASSA_TAX_SYSTEM,  # 2 = УСН доходы (по умолчанию)
            "items": [{
                "description": f"{t['label']} — TRUE AI ACADEMY"[:128],
                "quantity": "1.00",
                "amount": {"value": f"{t['now']}.00", "currency": "RUB"},
                "vat_code": 1,                        # 1 = Без НДС (на УСН)
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }],
        }
    })
    try:
        await bot.send_invoice(
            chat_id=call.from_user.id,
            title=f"{t['label']} — TRUE AI ACADEMY"[:32],
            description=t["perks"][:255],
            payload=f"course_{plan_key}",
            provider_token=YOOKASSA_TOKEN,
            currency="RUB",
            prices=[LabeledPrice(label=t["label"][:32], amount=t["now"] * 100)],  # в копейках
            need_email=True,
            send_email_to_provider=True,
            provider_data=provider_data,
            start_parameter="buy",
        )
        if YOOKASSA_TEST:
            await call.message.answer(
                "🧪 <b>Тестовый режим ЮKassa.</b>\n"
                "Оплати картой <code>1111 1111 1111 1026</code>, "
                "срок <b>12/26</b>, CVC <b>000</b> — деньги не спишутся."
            )
    except Exception as e:
        logging.error(f"YooKassa invoice error: {e}")
        await call.message.answer(
            "⚠️ Не удалось открыть оплату картой. Попробуй ещё раз или напиши менеджеру:",
            reply_markup=to_manager_kb(),
        )


@dp.pre_checkout_query()
async def pre_checkout(pcq: PreCheckoutQuery):
    # Валидация: принимаем только наши инвойсы (payload вида course_<plan>)
    payload = pcq.invoice_payload or ""
    plan_key = payload.replace("course_", "")
    if not payload.startswith("course_") or plan_key not in TARIFFS:
        await bot.answer_pre_checkout_query(
            pcq.id, ok=False,
            error_message="Некорректный заказ. Откройте оплату заново через /tariffs."
        )
        return
    await bot.answer_pre_checkout_query(pcq.id, ok=True)


@dp.message(lambda m: m.successful_payment is not None)
async def on_paid(message: Message):
    sp = message.successful_payment
    plan_key = (sp.invoice_payload or "course_vip").replace("course_", "")
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    user_id = str(message.from_user.id)
    set_stage(user_id, "paid")
    track("pay_success", user_id, plan_key)

    new_badge = give_badge(user_id, "buyer")
    add_xp(user_id, "buy")

    # Сумма и метод в зависимости от валюты
    if sp.currency == "XTR":
        amount_str = f"{sp.total_amount} ⭐ Stars"
        method = "Telegram Stars"
    else:
        amount_str = f"{sp.total_amount / 100:.0f} {sp.currency}"
        method = "ЮKassa (карта)"
    is_test = YOOKASSA_TEST and sp.currency == "RUB"

    # Тест-тариф: подтверждаем оплату и сразу выдаём доступ к 1-му дню.
    if plan_key == "test":
        await message.answer(
            "✅ <b>Оплата 100 ₽ прошла — проверка ЮKassa успешна!</b>\n\n"
            "🎓 Открываю доступ к <b>1-му дню курса</b> 👇",
        )
        await message.answer(
            "🎓 <b>ДЕНЬ 1 курса</b>\n\n"
            "Доступ открыт. Запускай первый день прямо сейчас 👇",
            reply_markup=day1_kb(),
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🧪 <b>ТЕСТ-ОПЛАТА 100 ₽ прошла</b>\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"💳 {sp.total_amount / 100:.0f} {sp.currency}\n"
                f"🧾 charge: <code>{sp.telegram_payment_charge_id}</code>\n"
                + ("🧪 Тестовый режим — деньги не списаны.\n" if (YOOKASSA_TEST and sp.currency == 'RUB') else "💰 Боевой платёж — оформи возврат в ЮKassa → Возвраты.")
            )
        except Exception:
            pass
        return

    # Докупка 8-го дня (продвижение/SMM) — отдельный продукт, тариф не меняет.
    if plan_key == "day8":
        _ensure_game(user_id)["day8"] = True
        save_users()
        await message.answer(
            "✅ <b>8-й день куплен!</b>\n\n"
            "Бонус-день про SMM, продвижение, продажи и фриланс.\n"
            "Он откроется, когда дойдёшь до него по курсу 👇",
            reply_markup=course_hub_kb(user_id),
        )
        try:
            await bot.send_message(ADMIN_ID,
                f"🚀 <b>ОПЛАТА 8-го дня</b>\n🆔 <code>{user_id}</code>\n💳 {method}: {amount_str}")
        except Exception:
            pass
        return

    # Запоминаем купленный тариф (для доступа к дням; в PRO 8-й день уже включён).
    if plan_key in ("base", "vip", "pro"):
        users.setdefault(user_id, {})["plan"] = plan_key
        save_users()

    toast = badge_toast("buyer") if new_badge else ""
    await message.answer(
        f"🎉 <b>Оплата прошла! Добро пожаловать в {t['label']}.</b>\n\n"
        "Доступ к курсу открыт 🎓 Дальше — по одному дню:\n"
        "прошёл урок → отметил домашку → через 4 часа\n"
        "открывается следующий. Так всё усваивается.\n\n"
        f"Менеджер {MANAGER} напишет тебе совсем скоро "
        "и добавит в чат с куратором.\n\n"
        "👇 Можно начинать:"
        + toast,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Открыть мои уроки", callback_data="course")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
        ]),
    )
    name = message.from_user.first_name or "Юзер"
    uname = f"@{message.from_user.username}" if message.from_user.username else "нет username"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"✅✅✅ <b>ОПЛАТА{' (ТЕСТ)' if is_test else ''}!</b>\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📦 Тариф: {t['label']}\n"
            f"💳 {method}: {amount_str}\n"
            f"🧾 charge: <code>{sp.telegram_payment_charge_id}</code>\n"
            + ("🧪 Это тестовый платёж — деньги не списаны.\n" if is_test else "")
            + "→ Добавь в закрытый чат с куратором."
        )
    except Exception:
        pass


# ─── ЮKassa API: оплата через СБП / T-Pay / SberPay / карту ───────────────────────────────────────

def _yk_auth_header() -> str:
    raw = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _valid_email(s: str) -> bool:
    s = (s or "").strip()
    if " " in s or s.count("@") != 1:
        return False
    local, _, domain = s.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


async def yk_create_payment(amount_rub: int, description: str, email: str, plan_key: str, user_id: str):
    """Создаёт платёж в ЮKassa через API. Возвращает (payment_id, confirmation_url) или (None, None)."""
    value = f"{amount_rub}.00"
    payload = {
        "amount": {"value": value, "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": YOOKASSA_RETURN_URL},
        "description": description[:128],
        "metadata": {"user_id": user_id, "plan": plan_key},
        "receipt": {
            "customer": {"email": email},
            "tax_system_code": YOOKASSA_TAX_SYSTEM,
            "items": [{
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": value, "currency": "RUB"},
                "vat_code": 1,                  # 1 = без НДС (УСН)
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }],
        },
    }
    headers = {
        "Authorization": _yk_auth_header(),
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post("https://api.yookassa.ru/v3/payments", json=payload, headers=headers) as r:
                data = await r.json()
                if r.status not in (200, 201):
                    logging.error(f"YK create payment failed {r.status}: {data}")
                    return None, None
                return data.get("id"), (data.get("confirmation") or {}).get("confirmation_url")
    except Exception as e:
        logging.error(f"YK create payment error: {e}")
        return None, None


async def yk_get_payment(payment_id: str):
    headers = {"Authorization": _yk_auth_header()}
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"https://api.yookassa.ru/v3/payments/{payment_id}", headers=headers) as r:
                return await r.json()
    except Exception as e:
        logging.error(f"YK get payment error: {e}")
        return None


_granted_payments: set = set()  # защита от двойной выдачи доступа (poller + ручная проверка)


async def grant_paid_access(chat_id: int, user_id: str, plan_key: str, amount_str: str, payment_id: str):
    if payment_id in _granted_payments:
        return
    _granted_payments.add(payment_id)
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    set_stage(user_id, "paid")
    track("pay_success", user_id, plan_key)
    new_badge = give_badge(user_id, "buyer")
    add_xp(user_id, "buy")

    if plan_key == "test":
        await bot.send_message(
            chat_id,
            "✅ <b>Оплата прошла — проверка ЮKassa успешна!</b>\n\n"
            "🎓 Открываю доступ к <b>1-му дню курса</b> 👇",
        )
        await bot.send_message(
            chat_id,
            "🎓 <b>ДЕНЬ 1 курса</b>\n\nДоступ открыт. Запускай первый день прямо сейчас 👇",
            reply_markup=day1_kb(),
        )
    elif plan_key == "day8":
        _ensure_game(user_id)["day8"] = True
        save_users()
        await bot.send_message(
            chat_id,
            "✅ <b>8-й день куплен!</b>\n\n"
            "Бонус-день про SMM, продвижение, продажи и фриланс.\n"
            "Он откроется, когда дойдёшь до него по курсу 👇",
            reply_markup=course_hub_kb(user_id),
        )
    else:
        if plan_key in ("base", "vip", "pro"):
            users.setdefault(user_id, {})["plan"] = plan_key
            save_users()
        toast = badge_toast("buyer") if new_badge else ""
        await bot.send_message(
            chat_id,
            f"🎉 <b>Оплата прошла! Добро пожаловать в {t['label']}.</b>\n\n"
            "Доступ к курсу открыт 🎓 Дальше — по одному дню:\n"
            "прошёл урок → отметил домашку → через 4 часа\n"
            "открывается следующий. Так всё усваивается.\n\n"
            f"Менеджер {MANAGER} напишет тебе совсем скоро "
            "и добавит в чат с куратором.\n\n"
            "👇 Можно начинать:"
            + toast,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📚 Открыть мои уроки", callback_data="course")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
        )
    try:
        await bot.send_message(
            ADMIN_ID,
            f"✅✅✅ <b>ОПЛАТА (ЮKassa API{' ТЕСТ' if YOOKASSA_API_TEST else ''})!</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📦 Тариф: {t['label']}\n"
            f"💳 {amount_str} ₽ (СБП/T-Pay/SberPay/карта)\n"
            f"🧾 payment: <code>{payment_id}</code>\n"
            + ("🧪 Тестовый платёж — деньги не списаны.\n" if YOOKASSA_API_TEST else "→ Добавь в закрытый чат с куратором.")
        )
    except Exception:
        pass


async def poll_payment(chat_id: int, user_id: str, payment_id: str, plan_key: str):
    # Опрашиваем статус ~10 минут (120 × 5 c). Без вебхука.
    for _ in range(120):
        await asyncio.sleep(5)
        data = await yk_get_payment(payment_id)
        if not data:
            continue
        status = data.get("status")
        if status == "succeeded":
            amount = (data.get("amount") or {}).get("value", "0")
            await grant_paid_access(chat_id, user_id, plan_key, amount, payment_id)
            return
        if status == "canceled":
            try:
                await bot.send_message(chat_id, "❌ Платёж отменён. Попробуй ещё раз через /tariffs.")
            except Exception:
                pass
            return


@dp.callback_query(lambda c: c.data.startswith("ykapi_"))
async def cb_ykapi(call: CallbackQuery, state: FSMContext):
    plan_key = call.data.replace("ykapi_", "")
    await call.answer()
    if not YOOKASSA_API_ENABLED:
        await call.message.answer(
            "💳 Оплата пока настраивается. Напиши менеджеру — оформим вручную:",
            reply_markup=to_manager_kb(),
        )
        return
    await state.update_data(pay_plan=plan_key)
    await state.set_state(PayState.waiting_email)
    await call.message.answer(
        "✉️ <b>Введите ваш email</b> — на него ЮKassa пришлёт чек об оплате.\n\n"
        "<i>Например:</i> <code>name@mail.ru</code>"
    )


@dp.message(PayState.waiting_email)
async def on_pay_email(message: Message, state: FSMContext):
    email = (message.text or "").strip()
    if not _valid_email(email):
        await message.answer("❌ Это не похоже на email. Введите адрес вида <code>name@mail.ru</code>:")
        return
    data = await state.get_data()
    plan_key = data.get("pay_plan", "test")
    await state.clear()
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    user_id = str(message.from_user.id)
    track("yookassa_invoice", user_id, plan_key)

    # Тест-тариф — фиксированные 100 ₽; реальные тарифы — с учётом личной скидки.
    amount = t["now"] if plan_key == "test" else final_price(user_id, plan_key)

    pid, url = await yk_create_payment(
        amount, f"{t['label']} — TRUE AI ACADEMY", email, plan_key, user_id
    )
    if not url:
        await message.answer(
            "⚠️ Не удалось создать платёж. Попробуй ещё раз через /tariffs или напиши менеджеру:",
            reply_markup=to_manager_kb(),
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {amount} ₽", url=url)],
        [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"ykchk_{pid}:{plan_key}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])
    note = "🧪 <b>Тестовый режим.</b>\n" if YOOKASSA_API_TEST else ""
    saved = ""
    if plan_key != "test" and amount < t["now"]:
        saved = f"🎯 Личная скидка применена: <b>−{t['now'] - amount} ₽</b>\n"
    await message.answer(
        f"{note}{saved}💳 <b>Платёж на {amount} ₽ создан.</b>\n\n"
        "Нажми «Оплатить» → выбери <b>СБП, T-Pay, SberPay или карту</b> и подтверди.\n"
        "После оплаты вернись в бот — доступ откроется автоматически (или нажми «Я оплатил»).",
        reply_markup=kb,
    )
    asyncio.create_task(poll_payment(message.chat.id, user_id, pid, plan_key))


@dp.callback_query(lambda c: c.data.startswith("ykchk_"))
async def cb_ykcheck(call: CallbackQuery):
    await call.answer("Проверяю оплату…")
    rest = call.data.replace("ykchk_", "")
    pid, _, plan_key = rest.partition(":")
    data = await yk_get_payment(pid)
    status = (data or {}).get("status")
    if status == "succeeded":
        # Безопасность: платёж должен принадлежать ИМЕННО этому пользователю.
        # pid и plan приходят из callback_data (управляются клиентом) — нельзя выдавать
        # доступ по чужому/тест-платежу. Сверяем metadata.user_id и план из самого платежа.
        meta = data.get("metadata") or {}
        caller = str(call.from_user.id)
        real_plan = meta.get("plan") or plan_key or "test"
        if meta.get("user_id") and meta["user_id"] != caller:
            logging.warning(f"ykcheck ownership mismatch: pid={pid} owner={meta.get('user_id')} caller={caller}")
            await call.message.answer("⚠️ Этот платёж оформлен на другой аккаунт. Открой оплату заново через /tariffs.")
            return
        amount = (data.get("amount") or {}).get("value", "0")
        await grant_paid_access(call.message.chat.id, caller, real_plan, amount, pid)
    elif status == "canceled":
        await call.message.answer("❌ Платёж отменён. Попробуй ещё раз через /tariffs.")
    else:
        await call.message.answer(
            "⏳ Оплата ещё не поступила. Если ты только что оплатил — подожди 1–2 минуты и нажми «Я оплатил» снова."
        )


@dp.callback_query(lambda c: c.data.startswith("bump_"))
async def cb_bump(call: CallbackQuery):
    plan_key = call.data.replace("bump_", "")
    user_id = str(call.from_user.id)
    text = (
        "✨ <b>Отлично!</b> Созвон добавлен к твоей заявке.\n\n"
        "Менеджер уже видит заявку с апгрейдом.\n"
        "Напиши ему — выберете время созвона.\n\n"
        "👇"
    )
    await show(call, text, to_manager_kb())
    try:
        await bot.send_message(
            ADMIN_ID,
            f"✨ <b>UPSELL +990 ₽</b>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📦 Тариф: {plan_key.upper()} + созвон"
        )
    except Exception:
        pass


@dp.callback_query(lambda c: c.data == "remind_24h")
async def cb_remind(call: CallbackQuery):
    user_id = str(call.from_user.id)
    if user_id in users:
        users[user_id]["remind_at"] = now_ts() + 24 * 3600
        save_users()
    text = (
        "⏰ <b>Напомню через 24 часа.</b>\n\n"
        "Однако честно предупреждаю:\n"
        "⚠️ Места и акционная цена могут к завтра уйти.\n"
        "⚠️ Бонусы на 6 470 ₽ — только на этот поток.\n\n"
        "Если решён — лучше взять сейчас."
    )
    await show(call, text, downsell_kb())


@dp.callback_query(lambda c: c.data == "referral")
async def cb_referral(call: CallbackQuery):
    user_id = str(call.from_user.id)
    name = call.from_user.first_name or "друг"

    track("referral", user_id)
    add_xp(user_id, "referral")
    give_badge(user_id, "referrer")

    code = users.get(user_id, {}).get("promo_code")
    if not code:
        code = next((c for c, uid in promos.items() if uid == user_id), None)
    if not code:
        code = generate_code(name)
        promos[code] = user_id
        save_promos()
        if user_id in users:
            users[user_id]["promo_code"] = code
            save_users()
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🎫 Новый промокод\n"
                f"👤 {name}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"🎫 Код: <code>{code}</code>"
            )
        except Exception:
            pass

    # Ссылка-приглашение с привязкой к промокоду (для атрибуции через ?start=ref<code>)
    invite_link = f"https://t.me/{BOT_USERNAME}?start=ref{code}"
    share_text = (
        "Привет! Учусь в True AI Academy — нейросети и заработок. "
        f"Первые 2 дня бесплатно. Промокод при оплате: {code} — скидка 500₽"
    )
    share_url = f"https://t.me/share/url?url={quote(invite_link)}&text={quote(share_text)}"

    text = (
        "💸 <b>ПАРТНЁРСКАЯ ПРОГРАММА</b>\n\n"
        "🎁 Ты получаешь <b>30% на карту</b> с каждой оплаты\n"
        "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
        f"🎫 <b>Твой промокод:</b> <code>{code}</code>\n"
        f"🔗 <b>Твоя ссылка:</b> {invite_link}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Реальный расчёт:</b>\n"
        "▸ 1 друг взял VIP → 1 491 ₽ тебе\n"
        "▸ 3 друга VIP → 4 473 ₽ — окупился твой курс\n"
        "▸ 10 друзей → 14 910 ₽ на карте\n\n"
        "👇 Нажми «Переслать другу» и выбери, кому отправить:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Переслать другу (1 тап)", url=share_url)],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])
    await show(call, text, kb)


@dp.callback_query(lambda c: c.data == "profile")
async def cb_profile(call: CallbackQuery):
    user_id = str(call.from_user.id)
    name = call.from_user.first_name or "друг"
    _, new_badge = touch_streak(user_id)
    text = profile_text(user_id, name)
    if new_badge:
        text += badge_toast(new_badge)
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥊 Челлендж дня (+10 XP)", callback_data="challenge")],
        [InlineKeyboardButton(text="🎓 Пройти урок (+XP)", callback_data="day1")],
        [InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    user_id = str(call.from_user.id)
    pos, xp = my_rank(user_id)

    # Разрыв до призовой зоны (топ-3) — мотивируем обогнать
    ranked = sorted((u.get("xp", 0) for u in users.values()), reverse=True)
    if pos > 3 and len(ranked) >= 3:
        gap = ranked[2] - xp + 1
        rank_line = (
            f"\n\n📍 <b>Ты на {pos}-м месте</b> ({xp} XP).\n"
            f"До призовой тройки — <b>{max(1, gap)} XP</b>. "
            "Пройди челлендж дня и обгони!"
        )
    elif pos <= 3 and xp > 0:
        rank_line = f"\n\n🔥 <b>Ты в призовой тройке — {pos} место!</b> Удержи позицию до конца недели."
    else:
        rank_line = "\n\n📍 Ты ещё не в рейтинге — пройди челлендж дня, чтобы попасть в таблицу!"

    await show(call, leaderboard_text() + rank_line, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥊 Челлендж дня (+10 XP)", callback_data="challenge")],
        [InlineKeyboardButton(text="🎮 Мой прогресс", callback_data="profile")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


# ─── МЕХАНИКА №7: КОЛЕСО УДАЧИ (после 2-го дня) ────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "wheel")
async def cb_wheel(call: CallbackQuery):
    user_id = str(call.from_user.id)
    give_badge(user_id, "day2_done")
    track("wheel_open", user_id)

    u = _ensure_game(user_id)
    if u.get("wheel"):
        # Уже крутил — ведём сразу к закрытому предложению
        await cb_special_tariffs(call)
        return

    text = (
        "🎰 <b>Колесо удачи</b>\n\n"
        "Ты прошёл оба дня — держи бонус.\n"
        "Один бесплатный прокрут, что выпадет — твоё:\n\n"
        "💸 скидка до 1 500 ₽\n"
        "🎁 100+ промптов\n"
        "📘 гайд «где брать заказы»\n"
        "👑 месяц с куратором\n\n"
        "👇 Крутить:"
    )
    await show_img(call, "wheel.jpg", text, wheel_kb())


@dp.callback_query(lambda c: c.data == "wheel_spin")
async def cb_wheel_spin(call: CallbackQuery):
    user_id = str(call.from_user.id)
    prize = spin_wheel(user_id)
    give_badge(user_id, "lucky")
    track("wheel_spin", user_id, prize["id"] if prize else "already")

    if prize is None:
        await call.answer("Ты уже крутил колесо 🙂", show_alert=True)
        await cb_special_tariffs(call)
        return

    # Персональное поздравление от AI (короткое, дешёвое). Fallback — без AI.
    await call.answer()
    goal = GOAL_LABELS.get(users.get(user_id, {}).get("goal", ""), "работу с нейросетями")
    congrats = None
    if rate_ok(user_id, "ai_wheel", 60):
        congrats = await ai_text(
            WHEEL_SYSTEM,
            f"Приз: {prize['label']}. Цель ученика: {goal}. Поздравь в 1-2 предложениях.",
            max_tokens=120,
        )
    congrats = congrats or "Поздравляю — отличный приз! Самое время закрепить результат. 🎉"

    extra = ""
    if prize["type"] == "discount":
        extra = (
            f"\n\n💸 Скидка <b>{prize['value']} ₽</b> закреплена за тобой. "
            "Применится автоматически, если она выгоднее твоей текущей. ⏳ Действует 24 часа."
        )

    await show(
        call,
        f"🎉 <b>ТЫ ВЫИГРАЛ:</b> {prize['label']}\n\n{congrats}{extra}\n\n"
        "👇 Забери приз вместе с закрытым предложением:",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Открыть закрытое предложение", callback_data="special_tariffs")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
        ]),
    )


# ─── ПЕРВОЕ AI-ЧУДО (фото → желание → генерация картинки → GIFT-бот → канал). 1 раз на аккаунт. ──────

def wow_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="wow_cancel")],
    ])


def wow_used_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 100+ нейросетей — забрать бесплатно", url=GIFT_LINK)],
        [InlineKeyboardButton(text="🚀 2 дня курса бесплатно", callback_data="day1")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


@dp.callback_query(lambda c: c.data == "wow")
async def cb_wow(call: CallbackQuery, state: FSMContext):
    user_id = str(call.from_user.id)
    track("wow_open", user_id)

    # 1 раз на аккаунт — если уже воспользовался, мягко уводим на GIFT-бот
    # (админ тестирует без лимита)
    if not is_admin(user_id) and _ensure_game(user_id).get("wow_used"):
        await show(
            call,
            "✨ <b>Ты уже создал своё фото!</b>\n\n"
            "Бесплатная попытка — одна.\n"
            "Но это лишь начало: дальше целый набор нейросетей 👇",
            wow_used_kb(),
        )
        return

    await state.set_state(WowState.waiting_photo)
    text = (
        "✨ <b>Оживи своё фото</b>\n\n"
        "Сейчас сам увидишь — это правда просто.\n\n"
        "📸 Пришли любое фото: своё, друга или кота 🙂\n"
        "Скажешь, что с ним сделать — и покажу результат.\n\n"
        "Бесплатно, одно фото.\n\n"
        "👇 Жду фото:"
    )
    await show_img(call, "wow.jpg", text, wow_cancel_kb())


@dp.callback_query(lambda c: c.data == "wow_cancel")
async def cb_wow_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(call, "Окей, отложили. Фото можно оживить в любой момент ✨", start_kb())


async def _send_channel_later(uid: int, delay: int = 300):
    """Через 5 минут после первого чуда — мягко зовём на канал с бесплатными гайдами."""
    await asyncio.sleep(delay)
    if not CHANNEL_LINK:
        return
    try:
        await bot.send_message(
            uid,
            "📚 <b>Кстати — пока не забыл.</b>\n\n"
            "Гайды, готовые промпты и бесплатные фишки\n"
            "по нейросетям я выкладываю на своём канале.\n\n"
            "Загляни — там есть что изучить и забрать бесплатно 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📚 Открыть канал с гайдами", url=CHANNEL_LINK)],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logging.warning(f"channel nudge failed for {uid}: {e}")


def wow_sell_kb():
    """После результата: продаём — GIFT-бот (партнёрка) + курс."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 100+ нейросетей — возможностей в 100 раз больше", url=GIFT_LINK)],
        [InlineKeyboardButton(text="🚀 2 дня курса бесплатно", callback_data="day1")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


# Шаг 1: получили фото — спрашиваем, что с ним сделать
@dp.message(WowState.waiting_photo)
async def wow_photo(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    text = (message.caption or message.text or "").strip()

    if not message.photo and text.startswith("/"):
        await state.clear()
        await message.answer("Окей, отложили. Команда ниже 👇", reply_markup=start_kb())
        return

    if not message.photo:
        await message.answer(
            "Пришли именно <b>фото</b> 🙌 (картинкой, не файлом)",
            reply_markup=wow_cancel_kb(),
        )
        return

    # Анти-абуз: ограничим размер
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > 5 * 1024 * 1024:
        await message.answer("Фото великовато 😅 Пришли другое (до 5 МБ).", reply_markup=wow_cancel_kb())
        return

    await state.update_data(photo_id=photo.file_id)
    await state.set_state(WowState.waiting_wish)
    await message.answer(
        "🔥 <b>Фото получил!</b>\n\n"
        "Теперь напиши: <b>что мне сделать с этой фоткой?</b>\n\n"
        "Например:\n"
        "▸ <i>«сделай меня супергероем из комикса»</i>\n"
        "▸ <i>«преврати в Pixar-персонажа»</i>\n"
        "▸ <i>«деловой портрет для аватарки»</i>\n"
        "▸ <i>«добавь фон ночного города в неоне»</i>\n\n"
        "👇 Опиши своими словами:",
        reply_markup=wow_cancel_kb(),
    )


# Шаг 2: получили желание — генерируем картинку и продаём
@dp.message(WowState.waiting_wish)
async def wow_wish(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    wish = (message.text or message.caption or "").strip()

    if wish.startswith("/"):
        await state.clear()
        await message.answer("Окей, отложили. Команда ниже 👇", reply_markup=start_kb())
        return

    if not wish:
        await message.answer(
            "Опиши словами, что сделать с фото 🙌 (например «сделай меня супергероем»)",
            reply_markup=wow_cancel_kb(),
        )
        return

    data = await state.get_data()
    photo_id = data.get("photo_id")
    await state.clear()

    if not photo_id:
        await message.answer("Что-то потерялось 🙈 Начни заново через меню 🪄", reply_markup=start_kb())
        return

    wish = wish[:300]
    thinking = await message.answer("🪄 Создаю твою картинку нейросетью… это ~30–60 секунд.")

    # Скачиваем фото
    image_b64 = None
    try:
        file = await bot.get_file(photo_id)
        bio = await bot.download_file(file.file_path)
        image_b64 = base64.b64encode(bio.read()).decode("utf-8")
    except Exception as e:
        logging.error(f"wow download error: {e}")

    # Желание → промпт → генерация
    img_bytes = None
    if image_b64 and rate_ok(user_id, "wow_gen", 30):
        prompt = await ai_text(WOW_PROMPT_SYSTEM, wish, max_tokens=200) or wish
        img_bytes = await ai_generate_image(prompt, image_b64)

    try:
        await thinking.delete()
    except Exception:
        pass

    if not img_bytes:
        # Генерация недоступна (нет ключа/кредитов/ошибка) — бесплатный шанс НЕ сжигаем
        await message.answer(
            "😔 <b>Не получилось сгенерировать прямо сейчас</b> — сервис перегружен.\n\n"
            "Но ты не теряешь попытку! А пока — забери <b>100+ нейросетей</b>,\n"
            "там сделаешь это сам за минуту 👇",
            reply_markup=wow_sell_kb(),
        )
        track("wow_gen_fail", user_id)
        return

    # Сначала пытаемся отдать картинку — и только при успехе сжигаем бесплатный шанс
    try:
        await message.answer_photo(
            photo=BufferedInputFile(img_bytes, filename="ai_magic.png"),
            caption=(
                "✨ <b>Готово — вот результат!</b>\n\n"
                "Ну как, проще, чем казалось? 🙂\n\n"
                "А это сделала всего одна нейросеть. Их целый\n"
                "набор: видео, музыка, тексты, дизайн.\n\n"
                "🏅 +5 XP\n\n"
                "👇 Посмотреть весь набор:"
            ),
            reply_markup=wow_sell_kb(),
        )
    except Exception as e:
        logging.warning(f"wow send photo failed: {e}")
        await message.answer(
            "Картинка готова, но связь подвисла 😅 Попробуй ещё раз через меню 🪄",
            reply_markup=start_kb(),
        )
        return

    # Успех доставлен — фиксируем расход (1 раз на аккаунт) и награды
    # (админу расход не фиксируем — тестирует без лимита)
    u = _ensure_game(user_id)
    if not is_admin(user_id):
        u["wow_used"] = True
        save_users()
    add_xp(user_id, "wow")
    refresh_discount(user_id)
    give_badge(user_id, "wonder")
    track("wow_done", user_id)

    # Через 5 минут — мягкий зов на канал с гайдами
    asyncio.create_task(_send_channel_later(message.from_user.id))


# ─── МАГАЗИН ЗА XP ─────────────────────────────────────────────────────────────────────────────────

def shop_kb(uid: str):
    xp = _ensure_game(uid).get("xp", 0)
    rows = []
    for item_id, label, cost, _typ, _val in SHOP_ITEMS:
        mark = "" if xp >= cost else "🔒 "
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label} — {cost} XP", callback_data=f"shop_{item_id}"
        )])
    rows.append([InlineKeyboardButton(text="🥊 Заработать XP (челлендж)", callback_data="challenge")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(lambda c: c.data == "shop")
async def cb_shop(call: CallbackQuery):
    user_id = str(call.from_user.id)
    track("shop_open", user_id)
    xp = _ensure_game(user_id).get("xp", 0)
    credits = gen_credits(user_id)
    text = (
        "🛒 <b>МАГАЗИН ЗА XP</b>\n\n"
        f"У тебя: <b>{xp} XP</b>"
        + (f" · 🎨 генераций: <b>{credits}</b>" if credits else "") + "\n\n"
        "Меняй опыт на бесплатные AI-генерации фото\n"
        "и реальные скидки на курс. 👇\n\n"
        "💡 XP копится за челлендж дня, уроки, серии и приглашения друзей."
    )
    await show(call, text, shop_kb(user_id))


@dp.callback_query(lambda c: c.data.startswith("shop_"))
async def cb_shop_buy(call: CallbackQuery):
    user_id = str(call.from_user.id)
    item_id = call.data.replace("shop_", "")
    item = SHOP_BY_ID.get(item_id)
    if not item:
        await call.answer("Товар не найден", show_alert=True)
        return
    _id, label, cost, typ, val = item

    if not spend_xp(user_id, cost):
        xp = _ensure_game(user_id).get("xp", 0)
        await call.answer(f"Не хватает XP: нужно {cost}, у тебя {xp}", show_alert=True)
        return

    track("shop_buy", user_id, item_id)
    if typ == "gen":
        add_gen_credits(user_id, val)
        result = (
            f"✅ <b>Куплено: {label}</b>\n\n"
            f"🎨 Тебе начислено <b>{val}</b> генераций.\n"
            f"Всего доступно: <b>{gen_credits(user_id)}</b>.\n\n"
            "Жми «Сгенерировать фото» и присылай кадр 👇"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎨 Сгенерировать фото", callback_data="gen")],
            [InlineKeyboardButton(text="🛒 В магазин", callback_data="shop")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
        ])
    else:  # disc
        u = _ensure_game(user_id)
        u["shop_discount"] = u.get("shop_discount", 0) + val
        save_users()
        result = (
            f"✅ <b>Куплено: {label}</b>\n\n"
            f"💸 Скидка <b>{val} ₽</b> закреплена за тобой и применится к тарифу.\n"
            f"Твоя постоянная скидка из магазина: <b>{shop_discount(user_id)} ₽</b>.\n\n"
            "При оплате применяется самая выгодная из твоих скидок."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 К тарифам", callback_data="tariffs")],
            [InlineKeyboardButton(text="🛒 В магазин", callback_data="shop")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
        ])
    await show(call, result, kb)


# ─── ГЕНЕРАЦИЯ ПО КРЕДИТАМ (купленные/бонусные генерации) ───────────────────────────────────────────

def gen_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="gen_cancel")],
    ])


@dp.callback_query(lambda c: c.data == "gen")
async def cb_gen(call: CallbackQuery, state: FSMContext):
    user_id = str(call.from_user.id)
    if not is_admin(user_id) and gen_credits(user_id) <= 0:
        await show(
            call,
            "🎨 <b>У тебя пока нет генераций.</b>\n\n"
            "Купи их за XP в магазине — 3, 5 или 10 штук 👇",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Открыть магазин", callback_data="shop")],
                [InlineKeyboardButton(text="🥊 Заработать XP", callback_data="challenge")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
        )
        return
    await state.set_state(GenState.waiting_photo)
    credits_line = "Режим админа: без лимита ♾" if is_admin(user_id) else f"Доступно генераций: <b>{gen_credits(user_id)}</b>"
    await show(
        call,
        f"🎨 <b>AI-генерация фото</b>\n\n"
        f"{credits_line}\n\n"
        "📸 Пришли фото — и опиши, что с ним сделать.\n\n"
        "👇 Жду фото:",
        gen_cancel_kb(),
    )


@dp.callback_query(lambda c: c.data == "gen_cancel")
async def cb_gen_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(call, "Окей, отложили. Генерации ждут тебя 🎨", start_kb())


@dp.message(GenState.waiting_photo)
async def gen_photo(message: Message, state: FSMContext):
    text = (message.caption or message.text or "").strip()
    if not message.photo and text.startswith("/"):
        await state.clear()
        await message.answer("Окей, отложили. Команда ниже 👇", reply_markup=start_kb())
        return
    if not message.photo:
        await message.answer("Пришли именно <b>фото</b> 🙌", reply_markup=gen_cancel_kb())
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > 5 * 1024 * 1024:
        await message.answer("Фото великовато 😅 До 5 МБ, пожалуйста.", reply_markup=gen_cancel_kb())
        return
    await state.update_data(photo_id=photo.file_id)
    await state.set_state(GenState.waiting_wish)
    await message.answer(
        "🔥 Фото получил! Что с ним сделать?\n\n"
        "Например: <i>«сделай меня супергероем»</i>, "
        "<i>«Pixar-стиль»</i>, <i>«деловой портрет»</i>, "
        "<i>«неоновый фон ночного города»</i>\n\n"
        "👇 Опиши:",
        reply_markup=gen_cancel_kb(),
    )


@dp.message(GenState.waiting_wish)
async def gen_wish(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    wish = (message.text or message.caption or "").strip()
    if wish.startswith("/"):
        await state.clear()
        await message.answer("Окей, отложили. Команда ниже 👇", reply_markup=start_kb())
        return
    if not wish:
        await message.answer("Опиши словами, что сделать с фото 🙌", reply_markup=gen_cancel_kb())
        return
    data = await state.get_data()
    photo_id = data.get("photo_id")
    await state.clear()
    if not photo_id:
        await message.answer("Что-то потерялось 🙈 Начни заново 🎨", reply_markup=start_kb())
        return
    if not is_admin(user_id) and gen_credits(user_id) <= 0:
        await message.answer("Генерации закончились. Купи ещё в магазине 🛒", reply_markup=start_kb())
        return

    wish = wish[:300]
    thinking = await message.answer("🎨 Генерирую… ~30–60 секунд.")

    image_b64 = None
    try:
        file = await bot.get_file(photo_id)
        bio = await bot.download_file(file.file_path)
        image_b64 = base64.b64encode(bio.read()).decode("utf-8")
    except Exception as e:
        logging.error(f"gen download error: {e}")

    img_bytes = None
    if image_b64 and rate_ok(user_id, "gen_run", 10):
        prompt = await ai_text(WOW_PROMPT_SYSTEM, wish, max_tokens=200) or wish
        img_bytes = await ai_generate_image(prompt, image_b64)

    try:
        await thinking.delete()
    except Exception:
        pass

    if not img_bytes:
        await message.answer(
            "😔 Не получилось сгенерировать — сервис перегружен.\n"
            "Генерация <b>не списана</b>, попробуй ещё раз чуть позже 🎨",
            reply_markup=start_kb(),
        )
        track("gen_fail", user_id)
        return

    # Кредит списываем только после успешной отправки картинки
    admin = is_admin(user_id)
    left_after = max(0, gen_credits(user_id) - 1)
    left_line = "Режим админа: без лимита ♾" if admin else (
        f"Осталось генераций: <b>{left_after}</b>"
        + ("" if left_after else " — пополни в 🛒 магазине за XP"))
    try:
        await message.answer_photo(
            photo=BufferedInputFile(img_bytes, filename="ai_gen.png"),
            caption=(
                "🎨 <b>Готово!</b>\n\n"
                f"{left_line}\n\n"
                "Хочешь ещё? Жми «Сгенерировать снова» 👇"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎨 Сгенерировать снова", callback_data="gen")],
                [InlineKeyboardButton(text="🛒 Магазин за XP", callback_data="shop")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
        )
    except Exception as e:
        logging.warning(f"gen send photo failed: {e}")
        await message.answer(
            "Картинка готова, но связь подвисла 😅 Генерация не списана — попробуй ещё раз 🎨",
            reply_markup=start_kb(),
        )
        return

    if not admin:
        use_gen_credit(user_id)
    track("gen_done", user_id)


# ─── МЕХАНИКА №1: ЧЕЛЛЕНДЖ ДНЯ (промпт-дуэль, оценивает AI) ─────────────────────────────────────────

def challenge_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="ch_cancel")],
    ])


@dp.callback_query(lambda c: c.data == "challenge")
async def cb_challenge(call: CallbackQuery, state: FSMContext):
    user_id = str(call.from_user.id)
    # Один челлендж в день на юзера (удержание + контроль расхода)
    if not rate_ok(user_id, "challenge", 20 * 3600):
        left_h = max(1, rate_left(user_id, "challenge", 20 * 3600) // 3600)
        await show(
            call,
            f"🥊 <b>Челлендж дня уже пройден!</b>\n\n"
            f"Возвращайся через ~{left_h} ч за новой темой и новым XP.\n"
            "А пока — забери XP за урок или подними скидку за прогресс 👇",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 Мой прогресс и скидка", callback_data="profile")],
                [InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
            ]),
        )
        return
    await state.set_state(ChallengeState.waiting)
    text = (
        "🥊 <b>Челлендж дня</b>\n\n"
        f"📌 <b>Тема:</b> {challenge_theme()}\n\n"
        "Напиши свой запрос (промпт) для нейросети на эту\n"
        "тему — одним сообщением. Я оценю по 10-балльной\n"
        "шкале и подскажу, что улучшить.\n\n"
        "🏅 За попытку — +10 XP и рост личной скидки.\n\n"
        "👇 Жду твой промпт:"
    )
    await show(call, text, challenge_cancel_kb())


@dp.callback_query(lambda c: c.data == "ch_cancel")
async def cb_ch_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(call, "Окей, челлендж отложил. Возвращайся в любой момент 👇", start_kb())


@dp.message(ChallengeState.waiting)
async def process_challenge(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_text = (message.text or message.caption or "").strip()

    if user_text.startswith("/"):
        await state.clear()
        await message.answer("Окей, челлендж отложил. Команда ниже 👇", reply_markup=start_kb())
        return

    if not user_text:
        await message.answer(
            "Пришли <b>текст промпта</b> — и AI его оценит 🙌",
            reply_markup=challenge_cancel_kb(),
        )
        return

    # Защита: ограничим длину запроса в AI (анти-абуз токенов)
    user_text = user_text[:1500]

    await state.clear()
    thinking = await message.answer("✍️ Смотрю твой промпт… пара секунд.")

    review = await ai_text(
        CHALLENGE_SYSTEM,
        f"Тема дня: {challenge_theme()}\n\nПромпт ученика:\n{user_text}",
        max_tokens=250,
    )

    try:
        await thinking.delete()
    except Exception:
        pass

    add_xp(user_id, "challenge")
    refresh_discount(user_id)
    new_badge = give_badge(user_id, "challenger")
    toast = badge_toast("challenger") if new_badge else ""
    disc = active_discount(user_id)
    disc_line = f"\n💸 Твоя скидка за прогресс: <b>{disc} ₽</b>" if disc else ""

    if not review:
        track("challenge_fallback", user_id)
        await message.answer(
            "🙌 <b>Промпт принят!</b>\n\n"
            "Разбор сейчас недоступен, но XP уже твой.\n"
            f"🏅 <b>+10 XP</b> за челлендж дня!{disc_line}{toast}",
            reply_markup=start_kb(),
        )
        return

    track("challenge_ai", user_id)
    await message.answer(
        "🥊 <b>Разбор твоего промпта</b>\n\n"
        f"{review}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏅 <b>+10 XP</b> за челлендж дня!{disc_line}{toast}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Мой прогресс и скидка", callback_data="profile")],
            [InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
        ]),
    )


# ─── КОМАНДЫ ───────────────────────────────────────────────────────────────────────────

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    name = message.from_user.first_name or "друг"
    touch_streak(user_id)
    await message.answer(profile_text(user_id, name), reply_markup=start_kb())


@dp.message(Command("top"))
async def cmd_top(message: Message):
    await message.answer(leaderboard_text(), reply_markup=start_kb())


@dp.message(Command("challenge"))
async def cmd_challenge(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if not rate_ok(user_id, "challenge", 20 * 3600):
        left_h = max(1, rate_left(user_id, "challenge", 20 * 3600) // 3600)
        await message.answer(
            f"🥊 Челлендж дня уже пройден. Возвращайся через ~{left_h} ч 👇",
            reply_markup=start_kb(),
        )
        return
    await state.set_state(ChallengeState.waiting)
    await message.answer(
        "🥊 <b>ЧЕЛЛЕНДЖ ДНЯ</b>\n\n"
        f"📌 <b>Тема:</b> {challenge_theme()}\n\n"
        "Пришли свой промпт — дам оценку и подскажу, как улучшить. "
        "За попытку <b>+10 XP</b> 🏅",
        reply_markup=challenge_cancel_kb(),
    )


@dp.message(Command("trial"))
async def cmd_trial(message: Message):
    await message.answer(
        "🎁 <b>Бесплатный доступ — 1-й день курса</b>\n\n"
        "Изучи материал и возвращайся за 2-м днём 🚀",
        reply_markup=day1_kb()
    )


@dp.message(Command("course"))
async def cmd_course(message: Message):
    user_id = str(message.from_user.id)
    if not is_buyer(user_id):
        await message.answer(
            "📚 <b>Уроки курса</b>\n\n"
            "Дни 1–2 — бесплатно, попробуй из меню.\n"
            "Дни 3–8 открываются после оплаты, по одному:\n"
            "сделал домашку → через 4 часа следующий день.\n\n"
            "👇 Тарифы:",
            reply_markup=tariffs_kb(get_spots()),
        )
        return
    target = course_target(user_id)
    if target is None:
        body = "🎉 Ты прошёл все 8 дней. Дальше — практика и заказы 🚀"
    else:
        st, left = course_gate(user_id, target)
        if st == "ok":
            body = f"Следующий — день {target}. Можно открывать 👇"
        elif st == "wait":
            body = f"День {target} откроется через {_human_left(left)} 🙂"
        elif st == "hw":
            body = f"Отметь домашку дня {target - 1} — откроется день {target}."
        elif st == "day8pay":
            body = "День 8 (продвижение/SMM) открывается отдельно за 1 790 ₽."
        else:
            body = f"Продолжаем с дня {target}."
    kb = day8_offer_kb() if (target == 8 and not has_day8(user_id)) else course_hub_kb(user_id)
    await message.answer(f"📚 <b>Мои уроки</b>\n\n{body}", reply_markup=kb)


@dp.message(Command("tariffs"))
async def cmd_tariffs(message: Message):
    s = get_spots()
    text = (
        f"💰 <b>ТАРИФЫ</b>\n\n"
        f"Осталось мест по этой цене: <b>{s}</b>\n\n"
        "⭐ <b>VIP — 4 970 ₽</b>  ← берут 7 из 10\n"
        "🚀 <b>PRO + продвижение — 7 970 ₽</b>\n"
        "📦 <b>Базовый — 2 970 ₽</b>\n\n"
        "👇 Выбери:"
    )
    await message.answer(text, reply_markup=tariffs_kb(s))


@dp.message(Command("paytest"))
async def cmd_paytest(message: Message):
    # Только для админа: проверка боевой оплаты ЮKassa на 100 ₽.
    if message.from_user.id != ADMIN_ID:
        return
    if not (YOOKASSA_API_ENABLED or YOOKASSA_TOKEN):
        await message.answer(
            "⚠️ Оплата не настроена. Задай YOOKASSA_SECRET_KEY (для СБП/T-Pay/SberPay) "
            "или YOOKASSA_PROVIDER_TOKEN (карта) в переменных Amvera."
        )
        return
    if YOOKASSA_API_ENABLED:
        mode = "ТЕСТОВЫЙ (деньги не спишутся)" if YOOKASSA_API_TEST else "БОЕВОЙ (спишутся реальные 100 ₽)"
        methods = "СБП, T-Pay, SberPay или картой"
    else:
        mode = "ТЕСТОВЫЙ (деньги не спишутся)" if YOOKASSA_TEST else "БОЕВОЙ (спишутся реальные 100 ₽)"
        methods = "картой"
    await message.answer(
        f"🧪 <b>Проверка оплаты ЮKassa — 100 ₽</b>\n\n"
        f"Режим: <b>{mode}</b>\n"
        f"Нажми «Оплатить», заплати {methods} — бот выдаст доступ к 1-му дню.\n"
        "После проверки оформи возврат в кабинете ЮKassa → Возвраты.",
        reply_markup=pay_choice_kb("test"),
    )


async def _img_test_one(model: str, prompt: str, image_b64: str):
    """Один запрос к конкретной image-модели. Возвращает bytes или None; кидает на HTTP-ошибке."""
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    headers.update(OPENROUTER_EXTRA)
    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "modalities": ["image", "text"]}
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(OPENROUTER_URL, json=payload, headers=headers) as r:
            data = await r.json()
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {str(data)[:120]}")
            for im in (data["choices"][0]["message"].get("images") or []):
                url = (im.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    return base64.b64decode(url.split(",", 1)[1])
    return None


@dp.message(Command("imgtest"))
async def cmd_imgtest(message: Message):
    """Только админ: прогоняет ВСЕ image-модели на тестовом фото и шлёт результат."""
    if message.from_user.id != ADMIN_ID:
        return
    if not OPENROUTER_KEY:
        await message.answer("⚠️ OPENROUTER_API_KEY не задан в окружении.")
        return
    src = os.path.join(IMG_DIR, "author.jpg")
    if not os.path.exists(src):
        await message.answer("⚠️ Нет images/author.jpg для теста.")
        return
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    prompt = ("Clean professional business headshot, soft neutral studio background, "
              "keep the face identical to the photo.")
    await message.answer("🧪 Тестирую все image-модели по очереди… ~30 с каждая.")
    lines = []
    for model in AI_IMAGE_MODELS:
        t = now_ts()
        try:
            img = await _img_test_one(model, prompt, b64)
            dt = now_ts() - t
            if img:
                lines.append(f"✅ <code>{model}</code> — {len(img) // 1024} KB, {dt:.0f}с")
                try:
                    await message.answer_photo(
                        BufferedInputFile(img, filename=f"{model.split('/')[-1]}.png"),
                        caption=model)
                except Exception:
                    pass
            else:
                lines.append(f"⚠️ <code>{model}</code> — без картинки, {dt:.0f}с")
        except Exception as e:
            lines.append(f"❌ <code>{model}</code> — {str(e)[:70]}")
    await message.answer("🧪 <b>Итог:</b>\n" + "\n".join(lines))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ <b>ПОМОЩЬ</b>\n\n"
        "/start — главное меню\n"
        "/trial — бесплатный доступ\n"
        "/course — мои уроки курса 📚\n"
        "/tariffs — тарифы\n"
        "/profile — твой прогресс, XP, скидка и бейджи 🎮\n"
        "/challenge — челлендж дня с разбором 🥊\n"
        "/top — рейтинг учеников 🏅\n\n"
        "💬 Менеджер ответит за 5 минут 👇"
    )
    await message.answer(text, reply_markup=to_manager_kb())


def build_stats_text() -> str:
    stages = {}
    for data in users.values():
        s = data.get("stage", "start")
        stages[s] = stages.get(s, 0) + 1
    stage_lines = "\n".join(f"  {k}: {v}" for k, v in sorted(stages.items()))
    goals = {}
    for data in users.values():
        g = data.get("goal", "—")
        goals[g] = goals.get(g, 0) + 1
    goal_lines = "\n".join(f"  {GOAL_LABELS.get(k, k)}: {v}" for k, v in sorted(goals.items()))
    total = len(users)
    purchased = stages.get("purchased", 0) + stages.get("paid", 0)
    paid = stages.get("paid", 0)
    conv = (purchased / total * 100) if total else 0
    c = events_log.get("counters", {})
    funnel = (
        f"  🌐 с сайта (land): {c.get('start_land', 0)}\n"
        f"  🤯 чудо открыли: {c.get('wow_open', 0)} / готово: {c.get('wow_done', 0)}\n"
        f"  ▶️ день 1: {c.get('day1', 0)}\n"
        f"  ▶️ день 2: {c.get('day2', 0)}\n"
        f"  🛒 магазин: {c.get('shop_open', 0)} / покупок: {c.get('shop_buy', 0)}\n"
        f"  💰 тарифы: {c.get('special_tariffs', 0)}\n"
        f"  💳 счёт ЮKassa: {c.get('yookassa_invoice', 0)}\n"
        f"  💳 заявка картой: {c.get('card_request', 0)}\n"
        f"  ✅ оплачено: {c.get('pay_success', 0)}"
    )
    return (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{total}</b>\n"
        f"💰 Заявок: <b>{purchased}</b> ({conv:.1f}%)\n"
        f"✅ Оплат: <b>{paid}</b>\n"
        f"🎫 Промокодов: <b>{len(promos)}</b>\n"
        f"📦 Мест осталось: <b>{get_spots()}</b>\n\n"
        f"<b>Воронка (события):</b>\n{funnel}\n\n"
        f"<b>По стадиям:</b>\n{stage_lines}\n\n"
        f"<b>По целям:</b>\n{goal_lines}"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(build_stats_text())


def build_referral_text() -> str:
    c = events_log.get("counters", {})
    rows = []
    for code, owner in promos.items():
        invited = c.get(f"start_ref{code}", 0)
        owner_name = users.get(owner, {}).get("name", "—")
        rows.append((invited, code, owner_name))
    rows.sort(reverse=True)
    total_invited = sum(r[0] for r in rows)
    top = rows[:15]
    lines = "\n".join(
        f"  🎫 <code>{code}</code> — {name}: <b>{inv}</b>" for inv, code, name in top
    ) or "  пока нет промокодов"
    return (
        f"💸 <b>Рефералы</b>\n\n"
        f"🎫 Амбассадоров (промокодов): <b>{len(promos)}</b>\n"
        f"👥 Переходов по реф-ссылкам: <b>{total_invited}</b>\n"
        f"💸 XP за рефералов выдано: <b>{c.get('referral', 0)}</b> раз\n\n"
        f"<b>Топ амбассадоров (код — имя: приглашений):</b>\n{lines}"
    )


def build_payments_text() -> str:
    c = events_log.get("counters", {})
    invoices = c.get("yookassa_invoice", 0)
    paid = c.get("pay_success", 0)
    card_req = c.get("card_request", 0)
    paid_users = sum(1 for d in users.values() if d.get("stage") == "paid")
    conv = (paid / invoices * 100) if invoices else 0
    return (
        f"💰 <b>Платежи</b>\n\n"
        f"💳 Счетов создано: <b>{invoices}</b>\n"
        f"✅ Успешных оплат: <b>{paid}</b>\n"
        f"📈 Конверсия счёт→оплата: <b>{conv:.1f}%</b>\n"
        f"👤 Пользователей со статусом «оплачено»: <b>{paid_users}</b>\n"
        f"📝 Заявок картой через менеджера: <b>{card_req}</b>"
    )


def build_recent_users_text(n: int = 15) -> str:
    items = sorted(users.items(), key=lambda kv: kv[1].get("start_at", 0), reverse=True)[:n]
    lines = []
    for uid, d in items:
        lines.append(f"  {d.get('name', '—')} (<code>{uid}</code>) — {d.get('stage', 'start')}")
    return f"👥 <b>Последние {len(items)} пользователей</b>\n\n" + ("\n".join(lines) or "  нет")


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Массовая рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="💸 Рефералы", callback_data="adm_refs")],
        [InlineKeyboardButton(text="💰 Платежи", callback_data="adm_pays")],
        [InlineKeyboardButton(text="👥 Последние пользователи", callback_data="adm_users")],
        [InlineKeyboardButton(text="📥 Экспорт данных", callback_data="adm_export")],
        [InlineKeyboardButton(text="🧪 Тест оплаты 100 ₽", callback_data="ykapi_test")],
        [InlineKeyboardButton(text="♻️ Полный сброс (всё)", callback_data="adm_reset")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="adm_home")],
    ])


def admin_panel_text() -> str:
    return (
        f"🛠 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
        f"✅ Оплат: <b>{events_log.get('counters', {}).get('pay_success', 0)}</b>\n"
        f"🎫 Промокодов: <b>{len(promos)}</b>\n"
        f"📦 Мест осталось: <b>{get_spots()}</b>\n\n"
        "Выбери действие 👇"
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(admin_panel_text(), reply_markup=admin_kb())


@dp.callback_query(lambda c: c.data == "adm_home")
async def cb_adm_home(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(admin_panel_text(), reply_markup=admin_kb())


@dp.callback_query(lambda c: c.data == "adm_refs")
async def cb_adm_refs(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(build_referral_text(), reply_markup=admin_back_kb())


@dp.callback_query(lambda c: c.data == "adm_pays")
async def cb_adm_pays(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(build_payments_text(), reply_markup=admin_back_kb())


@dp.callback_query(lambda c: c.data == "adm_users")
async def cb_adm_users(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(build_recent_users_text(), reply_markup=admin_back_kb())


@dp.callback_query(lambda c: c.data == "adm_reset")
async def cb_adm_reset(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Сначала скачать бэкап", callback_data="adm_export")],
        [InlineKeyboardButton(text="🔴 ДА, стереть ВСЁ безвозвратно", callback_data="adm_reset_yes")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="adm_home")],
    ])
    await call.message.answer(
        "⚠️ <b>ПОЛНЫЙ СБРОС</b>\n\n"
        f"Будет безвозвратно удалено:\n"
        f"• 👥 Пользователи: <b>{len(users)}</b>\n"
        f"• 🎫 Промокоды/рефералы: <b>{len(promos)}</b>\n"
        f"• 📊 Вся статистика и счётчики\n"
        f"• 📦 Места по акции (сброс к исходным)\n\n"
        "Бот станет как новый. Восстановить нельзя.\n"
        "Рекомендую сначала скачать бэкап 👇",
        reply_markup=kb,
    )


@dp.callback_query(lambda c: c.data == "adm_reset_yes")
async def cb_adm_reset_yes(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer("Стираю…")
    users.clear()
    promos.clear()
    spots_data.clear()
    events_log.get("counters", {}).clear()
    events_log.get("recent", []).clear()
    _granted_payments.clear()
    # помечаем все файлы на запись (фоновый flusher перезапишет пустыми)
    for key in ("users", "promos", "spots", "events"):
        _mark_dirty(key)
    await call.message.answer(
        "✅ <b>Полный сброс выполнен.</b>\n\n"
        "Пользователи, промокоды, рефералы и статистика обнулены. "
        "Бот как новый.",
        reply_markup=admin_back_kb(),
    )


@dp.callback_query(lambda c: c.data == "adm_export")
async def cb_adm_export(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer("Готовлю файлы…")
    sent = 0
    for path, title in [(USERS_FILE, "Пользователи"), (PROMO_FILE, "Промокоды"), (EVENTS_FILE, "События")]:
        if os.path.exists(path):
            try:
                await bot.send_document(ADMIN_ID, FSInputFile(path), caption=f"📥 {title}")
                sent += 1
            except Exception as e:
                logging.error(f"export {path}: {e}")
    if not sent:
        await call.message.answer("⚠️ Файлы данных пока не созданы.")
    await call.message.answer("Готово 👇", reply_markup=admin_back_kb())


@dp.callback_query(lambda c: c.data == "adm_broadcast")
async def cb_adm_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    await state.set_state(BroadcastState.waiting)
    await call.message.answer(
        f"📢 <b>Массовая рассылка на {len(users)} чел.</b>\n\n"
        "Пришли сообщение (текст с HTML, можно с фото) — оно уйдёт всем.\n"
        "Отмена: /cancel"
    )


@dp.callback_query(lambda c: c.data == "adm_stats")
async def cb_adm_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(build_stats_text())


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting)
    await message.answer(
        f"📢 Рассылка на <b>{len(users)}</b>.\n"
        "Напиши текст (HTML). Отмена: /cancel"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.")


@dp.message(BroadcastState.waiting)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text = message.text or message.caption or ""
    sent = failed = 0
    for uid in list(users.keys()):
        try:
            await bot.send_message(int(uid), text, reply_markup=start_kb())
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await message.answer(f"✅ Рассылка: {sent} отпр. / {failed} провал.")


@dp.message(Command("promo"))
async def cmd_promo_check(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Формат: /promo КОД")
        return
    code = args[1].upper()
    owner = promos.get(code)
    if owner:
        owner_name = users.get(owner, {}).get("name", "—")
        await message.answer(f"🎫 {code}\n👤 {owner_name}\n🆔 <code>{owner}</code>")
    else:
        await message.answer(f"❌ {code} не найден.")


# ─── FOLLOW-UP ЦЕПОЧКА (4 триггера) ──────────────────────────────────────────────────────

async def _fu_send(uid, text, kb, flag):
    """Отправляет напоминание и ставит флаг, чтобы не повторять. True — отправлено."""
    try:
        await bot.send_message(int(uid), text, reply_markup=kb, disable_web_page_preview=True)
        users[uid][flag] = True
        save_users()
        await asyncio.sleep(0.05)  # бережно к лимитам Telegram
        return True
    except Exception:
        return False


async def follow_up_scheduler():
    while True:
        await asyncio.sleep(1800)
        ts = now_ts()

        for uid, data in list(users.items()):
            stage = data.get("stage", "start")
            seen = data.get("seen_at", data.get("start_at", ts))
            try:
                # Приоритет 1 — просил напомнить (его собственный запрос, не назойливо)
                if (data.get("remind_at") and ts > data["remind_at"]
                        and not data.get("remind_sent")):
                    await _fu_send(uid,
                        "⏰ <b>Как и просил — напоминаю.</b>\n\n"
                        "Акционная цена и бонусы держатся не вечно.\n"
                        "Если планировал — сейчас удачный момент. 👇",
                        downsell_kb(), "remind_sent")
                    continue

                # FU1: зашёл, не начал day1 — через 2ч
                if (stage == "start" and not data.get("fu_start")
                        and ts - data.get("start_at", ts) > 2 * 3600):
                    await _fu_send(uid,
                        "👋 <b>Загляни — 2 дня курса всё ещё ждут тебя.</b>\n\n"
                        "Без оплаты и карты. 40 минут — и увидишь,\n"
                        "как на нейросетях реально зарабатывают.\n\n"
                        "👇 Начать:",
                        day1_kb(), "fu_start")
                    continue

                # FU_WOW: так и не попробовал «оживить фото» — через 6ч, мягко
                if (not data.get("wow_used") and not data.get("fu_wow")
                        and ts - data.get("start_at", ts) > 6 * 3600):
                    await _fu_send(uid,
                        "🤯 <b>Ты ещё не пробовал главное.</b>\n\n"
                        "Кинь фото — нейросеть превратит его в шедевр\n"
                        "за минуту. Это бесплатно и правда впечатляет 👇",
                        InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🤯 Оживить фото (бесплатно)", callback_data="wow")],
                            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
                        ]), "fu_wow")
                    continue

                # FU2: 1-й день пройден и прошло 12 ч — 2-й день открылся, зовём продолжить
                if (stage == "day1" and not data.get("fu_day1")
                        and ts - data.get("day1_at", ts) > DAY2_COOLDOWN):
                    await _fu_send(uid,
                        "🎓 <b>2-й день открылся!</b>\n\n"
                        "Сутки почти прошли — самое время продолжить.\n"
                        "Сегодня про то, как превратить навык в деньги.\n\n"
                        "👇 Открыть второй день:",
                        day2_kb(), "fu_day1")
                    continue

                # FU3: tariffs, не купил — через 20ч
                if (stage == "tariffs" and not data.get("fu_tariffs")
                        and ts - data.get("tariffs_at", ts) > 20 * 3600):
                    s = get_spots()
                    await _fu_send(uid,
                        f"💚 <b>Напоминаю про твоё предложение.</b>\n\n"
                        f"Осталось мест по акции: {s}.\n"
                        "Доступ к курсу — навсегда, без подписок.\n\n"
                        "👇 Посмотреть тарифы:",
                        tariffs_kb(s), "fu_tariffs")
                    continue

                # FU_REENGAGE: не заходил 3 дня — зовём ценностью (челлендж + XP), один раз
                if (not data.get("fu_reengage")
                        and ts - seen > 3 * 24 * 3600):
                    await _fu_send(uid,
                        "🥊 <b>Тебя ждёт новый челлендж дня!</b>\n\n"
                        f"Тема: {challenge_theme()}\n"
                        "Пройди за минуту — получишь +10 XP, а на XP\n"
                        "в магазине берутся бесплатные генерации и скидки 👇",
                        InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🥊 Челлендж дня", callback_data="challenge")],
                            [InlineKeyboardButton(text="🛒 Магазин за XP", callback_data="shop")],
                            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
                        ]), "fu_reengage")
                    continue

                # FU_DISCOUNT: личная скидка вот-вот сгорит — напоминаем (loss aversion, но полезно)
                until = data.get("discount_until", 0)
                if (active_discount(uid) > 0 and not data.get("fu_disc")
                        and 0 < until - ts < 3 * 3600):
                    await _fu_send(uid,
                        f"💸 <b>Твоя скидка {active_discount(uid)} ₽ ещё действует.</b>\n\n"
                        "Ты честно заработал её прогрессом 🙂\n"
                        "Успей применить на тарифе 👇",
                        tariffs_kb(get_spots()), "fu_disc")
                    continue

                # COURSE: следующий день курса открылся (домашка + 4 ч прошли) — зовём
                if is_buyer(uid):
                    tgt = course_target(uid)
                    if tgt and tgt >= 4:
                        st_c, _ = course_gate(uid, tgt)
                        flag = f"fu_day{tgt}_ready"
                        if st_c == "ok" and not data.get(flag):
                            await _fu_send(uid,
                                f"🎓 <b>День {tgt} открылся!</b>\n\n"
                                "Домашка засчитана, пауза прошла — продолжаем 👇",
                                InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text=f"📖 Открыть день {tgt}", callback_data=f"day_{tgt}")],
                                    [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
                                ]), flag)
                            continue

            except Exception:
                pass


# ─── Фоновая запись «грязных» файлов (не блокирует event-loop) ────────────────────────────────────

def _flush_targets():
    return {
        "users": (USERS_FILE, users),
        "spots": (SPOTS_FILE, spots_data),
        "promos": (PROMO_FILE, promos),
        "events": (EVENTS_FILE, events_log),
    }


async def disk_flusher():
    targets = _flush_targets()
    while True:
        await asyncio.sleep(2)
        if not _dirty:
            continue
        for key in list(_dirty):
            _dirty.discard(key)
            path, data = targets[key]
            try:
                await asyncio.to_thread(save_json, path, data)
            except Exception as e:
                logging.warning(f"flush {key} failed: {e}")


# ─── ЗАПУСК с retry при сетевых сбоях ─────────────────────────────────────────────────────────

async def main():
    print("Бот запущен!")
    asyncio.create_task(follow_up_scheduler())
    asyncio.create_task(disk_flusher())

    retry_delay = 5
    while True:
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        except Exception as e:
            logging.error(f"Polling error: {e}. Reconnect in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        else:
            break


if __name__ == "__main__":
    asyncio.run(main())
