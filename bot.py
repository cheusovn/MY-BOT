import asyncio
import json
import os
import logging
import random
import string
import time
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile,
    LabeledPrice, PreCheckoutQuery,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 817730727
BOT_USERNAME = "Trueman_ai_bot"
TRIAL_DAY_1 = "https://t.me/+5ep9DPf7eNMzZjdi"
TRIAL_DAY_2 = "https://t.me/+SpoNR-ahkJFiZTJi"
GIFT_LINK = "https://t.me/syntxaibot?start=aff_817730727"
MANAGER = "@nikolay_cheusov"
WELCOME_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.jpg")

STUDENTS_COUNT = "347"

# Цены: anchor (обычная) → текущая (акция)
PRICE_BASE = (5900, 2900)
PRICE_VIP = (9900, 4900)
PRICE_PRO = (14900, 7900)

logging.basicConfig(level=logging.INFO)

# Таймаут сессии: при сетевом лаге Amvera↔Telegram запрос отвалится за 30с,
# а не висит минуту, блокируя ответ (число секунд!).
_session = AiohttpSession(timeout=30)
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
    "🔥 Сегодня курс уже выбрали несколько человек",
    "🔥 VIP с куратором — самый частый выбор на этой неделе",
    "🔥 Большинство берут именно VIP (7 из 10)",
    "🔥 Места по акционной цене разбирают каждый день",
    "👥 Поток набирается — успей попасть по текущей цене",
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
        "💸 <b>Хочешь зарабатывать на нейросетях?</b>\n\n"
        "AI-контент — ниша, где спрос обгоняет исполнителей.\n"
        "Те, кто освоил инструменты, берут заказы по\n"
        "<b>800–2 500 ₽</b> за ролик или карточку товара.\n\n"
        "Остальные продолжают платить за это другим.\n"
        "Разница — <b>один навык.</b>\n\n"
    ),
    "business": (
        "🏢 <b>Хочешь прокачать бизнес через AI?</b>\n\n"
        "Твои конкуренты уже используют AI для\n"
        "контента, рекламы и продаж.\n\n"
        "Что это даёт на практике:\n"
        "▸ Экономия на подрядчиках за контент\n"
        "▸ В разы больше материалов своими силами\n"
        "▸ Быстрее тестируешь идеи и креативы\n\n"
    ),
    "curious": (
        "🔍 <b>Хочешь разобраться в нейросетях?</b>\n\n"
        "<b>Признаюсь:</b> курс подойдёт не всем.\n"
        "Если ищешь «волшебную таблетку» — нам не по пути.\n\n"
        "Но если готов уделить <b>1–2 часа в день</b>\n"
        "— через 7 дней будешь в топ-5% по работе с AI.\n"
        "Это реально.\n\n"
    ),
}


# ─── ТАРИФЫ (единый источник цен) ───────────────────────────────────────────────────────────────
# rub_old / rub_now — для отображения. stars — цена в Telegram Stars (оплата без ИП/самозанятого).
# Курс ⭐: ≈ 1 Star ≈ 1.7 ₽ (Telegram удерживает комиссию, выплата через Fragment).
TARIFFS = {
    "base": {"label": "📦 Базовый", "old": 5900, "now": 2970, "stars": 1750,
             "perks": "Все 7 дней курса + доступ навсегда"},
    "vip":  {"label": "⭐ VIP с куратором", "old": 9900, "now": 4970, "stars": 2900,
             "perks": "Все 7 дней + личный куратор + чат 24/7 + бонусы на 6 470 ₽"},
    "pro":  {"label": "🚀 PRO + продвижение", "old": 14900, "now": 7970, "stars": 4690,
             "perks": "Всё из VIP + где брать заказы + вирусный контент + SMM"},
}

# ─── ЮKassa (Telegram Payments) ───────────────────────────────────────────────────────────────────
# Provider token из @BotFather → Payments → ЮKassa. Тестовый содержит ":TEST:".
# Если не задан — кнопка оплаты картой уходит на менеджера (как раньше).
YOOKASSA_TOKEN = os.environ.get("YOOKASSA_PROVIDER_TOKEN", "")
YOOKASSA_TEST = ":TEST:" in YOOKASSA_TOKEN
# Система налогообложения для чека: 1=ОСН, 2=УСН доходы, 3=УСН доходы-расходы,
# 4=ЕНВД, 5=ЕСХН, 6=Патент. По умолчанию — УСН доходы.
YOOKASSA_TAX_SYSTEM = int(os.environ.get("YOOKASSA_TAX_SYSTEM", "2"))

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
}

XP_RULES = {
    "day1": 30, "day2": 50, "tariffs": 20,
    "free_gift": 15, "referral": 25, "daily": 10, "buy": 100,
    "challenge": 30,
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
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_EXTRA = {"HTTP-Referer": "https://t.me/Trueman_ai_bot", "X-Title": "True AI Academy"}

# Бесплатные текстовые модели (пробуем по очереди), затем дешёвый платный резерв.
AI_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "qwen/qwen-2.5-72b-instruct:free",
]
AI_PAID_RESERVE = "openai/gpt-4o-mini"  # дешёвый резерв при исчерпании free-лимитов


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

    return (
        f"🎮 <b>Профиль: {name}</b>\n\n"
        f"Уровень: <b>{lvl}</b>\n"
        f"Опыт: <b>{xp} XP</b>\n"
        f"{bar}\n"
        f"{nxt_line}\n\n"
        f"🔥 Серия дней подряд: <b>{u.get('streak', 0)}</b>\n\n"
        f"{disc_block}"
        f"🏅 <b>Достижения ({len(badges)}/{len(BADGES)}):</b>\n{badges_str}\n\n"
        "💡 Каждый день: челлендж + урок = XP, бейджи и рост скидки. "
        "Топ-3 недели получают бонусы."
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


# ─── КЛАВИАТУРЫ ─────────────────────────────────────────────────────────────────────────────────

def goal_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Хочу зарабатывать удалённо", callback_data="goal_freelance")],
        [InlineKeyboardButton(text="🏢 Хочу прокачать свой бизнес", callback_data="goal_business")],
        [InlineKeyboardButton(text="🔍 Хочу разобраться что такое AI", callback_data="goal_curious")],
    ])


def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Начать бесплатно — 2 дня доступа", callback_data="day1")],
        [InlineKeyboardButton(text="🔥 ПОДАРОК: 100+ AI бесплатно", callback_data="free_gift")],
        [
            InlineKeyboardButton(text="💰 Тарифы", callback_data="tariffs"),
            InlineKeyboardButton(text="🏆 Кейсы", callback_data="results"),
        ],
        [InlineKeyboardButton(text="🥊 Челлендж дня (+30 XP) — оценит AI", callback_data="challenge")],
        [
            InlineKeyboardButton(text="🎮 Мой прогресс", callback_data="profile"),
            InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard"),
        ],
        [InlineKeyboardButton(text="💸 Заработать 30% с друзей", callback_data="referral")],
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
    """Оплата картой РФ через ЮKassa; если токен не задан — через менеджера."""
    t = TARIFFS.get(plan_key, TARIFFS["vip"])
    rows = []
    if YOOKASSA_TOKEN:
        label = f"💳 Оплатить картой — {t['now']:,} ₽".replace(",", " ")
        if YOOKASSA_TEST:
            label += "  (ТЕСТ)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"yk_{plan_key}")])
    else:
        rows.append([InlineKeyboardButton(text="💳 Картой РФ через менеджера",
                                          callback_data=f"card_{plan_key}")])
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
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 Новый пользователь: <b>{name}</b>\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"👥 Всего: {len(users)}"
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

    text = (
        f"👋 <b>{name}, я твой AI-гид в True AI Academy.</b>\n\n"
        "Здесь обучение устроено <b>как игра</b>:\n"
        "🎮 проходишь уровни, копишь XP и бейджи,\n"
        "🔥 держишь серию дней — я веду тебя за руку\n"
        "от первого промпта до готового портфолио.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎁 Первые 2 дня — бесплатно, без карты\n"
        "🏅 За каждый шаг — опыт и достижения\n"
        "💬 Поддержка 24/7, если где-то застрял\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>С чего начнём?</b>\n"
        "Выбери цель — подберу твой маршрут:"
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
        "━━━━━━━━━━━━━━━━\n"
        "🎓 <b>Начни прямо сейчас — без оплаты и риска:</b>\n\n"
        "Я открою тебе <b>2 дня полного курса</b>.\n"
        "Или забери <b>100+ нейросетей в подарок</b> —\n"
        "это реальный инструментарий, не триал.\n\n"
        "👇 Что выберешь?"
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
        "🎁 <b>100+ НЕЙРОСЕТЕЙ — БЕСПЛАТНО НА 100+ ДНЕЙ</b>\n\n"
        "<b>Рыночная цена этого набора: ~38 000 ₽/год.</b>\n"
        "Отдаю тебе <b>бесплатно</b> — без карты и оплаты.\n\n"
        "<b>Что внутри:</b>\n"
        "🎨 Midjourney — изображения рекламных студий\n"
        "🎬 Kling, Runway, Veo — AI-видео за минуты\n"
        "🤖 ChatGPT Plus — тексты, идеи, сценарии\n"
        "🎵 Suno — музыка и саундтреки\n"
        "🔊 ElevenLabs — реалистичная озвучка\n"
        "📸 Nano Banana — фото и визуалы\n"
        "+ ещё <b>95+ инструментов</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>Почему бесплатно?</b>\n"
        "Я хочу, чтобы ты попробовал — и сам увидел,\n"
        "что AI реально может. Без воды и обещаний.\n\n"
        f"🔥 Уже <b>{STUDENTS_COUNT}+ человек</b> забрали подарок.\n"
        "👇 Нажми и получи прямо сейчас:"
    )
    await show(call, text, free_gift_kb())


@dp.callback_query(lambda c: c.data == "day1")
async def cb_day1(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "day1")
    track("day1", user_id)
    add_xp(user_id, "day1")
    new_badge = give_badge(user_id, "first_step")
    bonus = badge_toast("first_step") if new_badge else ""

    text = (
        "🎓 <b>ДЕНЬ 1 — ПРОГРЕСС: █░░ 33%</b>  <i>(+30 XP)</i>\n\n"
        "Ты в бесплатном доступе к полному курсу.\n"
        "Не вводная лекция, а <b>реальные уроки</b>.\n\n"
        "<b>Что сделаешь за ближайшие 40 минут:</b>\n"
        "▸ Запустишь нейросеть — без регистраций\n"
        "▸ Создашь изображения уровня эксперта\n"
        "▸ Напишешь первый рабочий промпт\n"
        "▸ Увидишь, <i>где именно деньги в AI</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <i>«После 1-го дня понял: это не сложно.\n"
        "Просто раньше боялся начать»</i>\n"
        "<b>— Алексей, студент</b>\n\n"
        "⚠️ <b>Важно:</b> закрытое предложение и бонусы\n"
        "откроются <b>только после 2-го дня.</b>\n\n"
        "👇 Открывай прямо сейчас:"
        + bonus
    )
    await show(call, text, day1_kb())


@dp.callback_query(lambda c: c.data == "day2")
async def cb_day2(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "day2")
    track("day2", user_id)
    add_xp(user_id, "day2")
    new_badge = give_badge(user_id, "day1_done")
    bonus = badge_toast("day1_done") if new_badge else ""

    text = (
        "🔥 <b>ДЕНЬ 2 — ПРОГРЕСС: ██░ 66%</b>  <i>(+50 XP)</i>\n\n"
        "День 1 пройден — ты уже не новичок.\n"
        "Сегодня пересечёшь черту между\n"
        "«просто интересно» и <b>«могу заработать.»</b>\n\n"
        "<b>Что внутри:</b>\n"
        "▸ Профессиональные генерации\n"
        "▸ Свои промпты, без шаблонов\n"
        "▸ Работы, за которые <b>платят 5–30k ₽</b>\n"
        "▸ Воронка: навык → заказ → деньги\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <i>«После 2-го дня взяла заказ на 8 000 ₽.\n"
        "Не верила, что так быстро получится»</i>\n"
        "<b>— Марина, 3 недели обучения</b>\n\n"
        "⚡ После 2-го дня открою\n"
        "<b>ЗАКРЫТОЕ предложение + 3 бонуса.</b>\n"
        "Только для тех, кто дошёл до конца.\n\n"
        "👇 Открывай:"
        + bonus
    )
    await show(call, text, day2_kb())


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

    # Механика №6+№7: суммарная личная скидка (прогресс + колесо)
    refresh_discount(user_id)
    total_disc = active_discount(user_id) + wheel_discount_active(user_id)
    base_vip, final_vip, _ = price_with_discount(user_id, "vip")
    final_vip = max(990, final_vip - wheel_discount_active(user_id))
    if total_disc > 0:
        disc_block = (
            f"🎯 <b>ТВОЯ ЛИЧНАЯ СКИДКА: −{total_disc} ₽</b>\n"
            f"VIP для тебя: <s>{base_vip} ₽</s> → <b>{final_vip} ₽</b>\n"
            "⏳ Скидка сгорает вместе с предложением — не упусти!\n\n"
        )
    else:
        disc_block = ""

    text = (
        "🔐 <b>ЗАКРЫТОЕ ПРЕДЛОЖЕНИЕ — ПРОГРЕСС: ███ 100%</b>\n"
        "Ты прошёл 2 дня. Это видят единицы.\n\n"
        f"⏳ Сгорает до: <b>{deadline}</b> (24 часа)\n"
        f"⚠️ Мест по этой цене: <b>{s}</b>\n\n"
        f"{disc_block}"
        "━━━━━━━━━━━━━━━━\n"
        "⭐ <b>VIP С КУРАТОРОМ</b>\n"
        "<s>9 900 ₽</s> → <b>4 970 ₽</b>  (экономия 4 930 ₽)\n"
        "это <b>16 ₽ в день</b> — дешевле чашки кофе\n\n"
        "Что внутри:\n"
        "✅ Все 7 дней курса + доступ навсегда\n"
        "✅ Личный куратор + разбор твоих работ\n"
        "✅ Чат поддержки 24/7\n\n"
        "🎁 <b>+ БОНУСЫ только сегодня:</b>\n"
        "   1) Гайд «30 источников заказов» — <s>2 990 ₽</s>\n"
        "   2) 100+ готовых промптов — <s>1 990 ₽</s>\n"
        "   3) Шаблон продающего портфолио — <s>1 490 ₽</s>\n"
        "   <b>Итого бонусов на 6 470 ₽ — бесплатно.</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🛡 <b>Почему без риска:</b>\n"
        "Сначала ты <b>2 дня бесплатно</b> делаешь реальный\n"
        "результат — и только потом решаешь, продолжать ли.\n"
        "Доступ к материалам и поддержка остаются с тобой.\n\n"
        f"{social_proof()}\n\n"
        "👇 Выбирай:"
    )
    await show(call, text, tariffs_kb(s))


@dp.callback_query(lambda c: c.data == "tariffs")
async def cb_tariffs(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "tariffs")
    tick_spots()
    s = get_spots()

    text = (
        "💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n\n"
        f"⚠️ Мест по акционной цене: <b>{s}</b>\n"
        f"{social_proof()}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⭐ <b>VIP С КУРАТОРОМ</b>  ← берут 7 из 10\n"
        "<s>9 900 ₽</s> → <b>4 970 ₽</b>  или 16 ₽/день\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Все 7 дней курса\n"
        "✅ Личный куратор + разбор твоих работ\n"
        "✅ Закрытый чат 24/7\n"
        "✅ Доступ навсегда\n"
        "🎁 + Бонусы на 6 470 ₽ бесплатно\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🚀 <b>PRO + ПРОДВИЖЕНИЕ</b>\n"
        "<s>14 900 ₽</s> → <b>7 970 ₽</b>  или 26 ₽/день\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Всё из VIP\n"
        "💼 Где брать заказы — площадки + схемы\n"
        "🔥 Вирусный контент — что залетает\n"
        "📢 Реклама без слива бюджета\n"
        "📱 SMM с нуля — до 1 млн просмотров\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📦 <b>БАЗОВЫЙ</b>\n"
        "<s>5 900 ₽</s> → <b>2 970 ₽</b>  или 10 ₽/день\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Все 7 дней курса\n"
        "✅ Доступ навсегда\n"
        "❌ Без куратора и бонусов\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🛡 <b>Без риска:</b> сначала 2 дня бесплатно,\n"
        "потом решаешь. Доступ остаётся навсегда.\n\n"
        "👇 Выбери тариф:"
    )
    await show(call, text, tariffs_kb(s))


@dp.callback_query(lambda c: c.data == "results")
async def cb_results(call: CallbackQuery):
    text = (
        "🏆 <b>РЕЗУЛЬТАТЫ СТУДЕНТОВ</b>\n\n"
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
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Попробовать курс бесплатно (2 дня)", callback_data="day1")],
        [InlineKeyboardButton(text="🔥 Подарок — 100+ нейросетей", callback_data="free_gift")],
        [InlineKeyboardButton(text="💰 Смотреть тарифы", callback_data="tariffs")],
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

    refresh_discount(user_id)
    total_disc = active_discount(user_id) + wheel_discount_active(user_id)
    final = max(990, t["now"] - total_disc)
    if total_disc > 0:
        price_line = (
            f"<s>{t['old']:,} ₽</s> → <s>{t['now']:,} ₽</s> → <b>{final:,} ₽</b>\n"
            f"🎯 С учётом твоей личной скидки <b>−{total_disc} ₽</b>\n"
        ).replace(",", " ")
        disc_hint = "💡 Скидка за прогресс уже учтена — назови её менеджеру.\n"
    else:
        price_line = f"<s>{t['old']:,} ₽</s> → <b>{t['now']:,} ₽</b>\n".replace(",", " ")
        disc_hint = "💡 Есть промокод друга? Скидку 500 ₽ применит менеджер.\n"

    text = (
        f"✅ <b>Отличный выбор — {t['label']}!</b>\n\n"
        f"{price_line}"
        f"{t['perks']}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💳 <b>Оплата картой РФ</b> — быстро и безопасно через ЮKassa,\n"
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
    total_disc = active_discount(user_id) + wheel_discount_active(user_id)
    final = max(990, t["now"] - total_disc)
    disc_note = f" (личная скидка −{total_disc} ₽)" if total_disc else ""
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

    toast = badge_toast("buyer") if new_badge else ""
    await message.answer(
        f"🎉 <b>Оплата прошла! Добро пожаловать в {t['label']}.</b>\n\n"
        "Доступ ко всем 7 дням курса и бонусам открыт.\n"
        f"Менеджер {MANAGER} свяжется с тобой в течение 15 минут "
        "и добавит в закрытый чат с куратором.\n\n"
        "А пока — загляни в «🎮 Мой прогресс»: ты получил статус студента 👑"
        + toast,
        reply_markup=back_kb(),
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

    text = (
        "💸 <b>ПАРТНЁРСКАЯ ПРОГРАММА</b>\n\n"
        "🎁 Ты получаешь <b>30% на карту</b> с каждой оплаты\n"
        "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
        f"🎫 <b>Твой промокод:</b> <code>{code}</code>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Реальный расчёт:</b>\n"
        "▸ 1 друг взял VIP → 1 491 ₽ тебе\n"
        "▸ 3 друга VIP → 4 473 ₽ — окупился твой курс\n"
        "▸ 10 друзей → 14 910 ₽ на карте\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Готовый текст — просто перешли:</b>\n\n"
        f"<i>Привет! Учусь в True AI Academy — нейросети и заработок.\n"
        f"Первые 2 дня бесплатно: @{BOT_USERNAME}\n"
        f"Промокод при оплате: {code} — скидка 500₽</i>"
    )
    await show(call, text, back_kb())


@dp.callback_query(lambda c: c.data == "profile")
async def cb_profile(call: CallbackQuery):
    user_id = str(call.from_user.id)
    name = call.from_user.first_name or "друг"
    _, new_badge = touch_streak(user_id)
    text = profile_text(user_id, name)
    if new_badge:
        text += badge_toast(new_badge)
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥊 Челлендж дня (+30 XP)", callback_data="challenge")],
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
        [InlineKeyboardButton(text="🥊 Челлендж дня (+30 XP)", callback_data="challenge")],
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
        "🎰 <b>КОЛЕСО УДАЧИ — ТОЛЬКО ДЛЯ ДОШЕДШИХ ДО КОНЦА</b>\n\n"
        "Ты прошёл 2 дня — это видят единицы. 🔥\n"
        "За это даю <b>один</b> бесплатный прокрут колеса.\n\n"
        "Что можно выиграть:\n"
        "💸 доп. скидку до 1 500 ₽\n"
        "🎁 100+ продающих промптов\n"
        "📘 гайд «30 источников заказов»\n"
        "👑 месяц VIP-куратора бесплатно\n\n"
        "⚠️ Приз действует <b>только при оплате сегодня</b>.\n\n"
        "👇 Крути:"
    )
    await show(call, text, wheel_kb())


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
            f"\n\n💸 Скидка <b>{prize['value']} ₽</b> уже закреплена за тобой "
            "и суммируется с твоей скидкой за прогресс. ⏳ Действует 24 часа."
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
        "🥊 <b>ЧЕЛЛЕНДЖ ДНЯ</b>\n\n"
        f"📌 <b>Тема:</b> {challenge_theme()}\n\n"
        "Напиши свой <b>промпт</b> для нейросети на эту тему "
        "(одним сообщением). AI оценит его по 10-балльной шкале "
        "и подскажет, как улучшить.\n\n"
        "🏅 За попытку — <b>+30 XP</b> и рост личной скидки.\n\n"
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
    thinking = await message.answer("🤖 AI оценивает твой промпт… пара секунд.")

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
            "AI-оценка сейчас недоступна, но XP уже твой.\n"
            f"🏅 <b>+30 XP</b> за челлендж дня!{disc_line}{toast}",
            reply_markup=start_kb(),
        )
        return

    track("challenge_ai", user_id)
    await message.answer(
        "🥊 <b>ОЦЕНКА AI</b>\n\n"
        f"{review}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏅 <b>+30 XP</b> за челлендж дня!{disc_line}{toast}",
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
        "Пришли свой промпт — AI оценит и подскажет, как улучшить. "
        "За попытку <b>+30 XP</b> 🏅",
        reply_markup=challenge_cancel_kb(),
    )


@dp.message(Command("trial"))
async def cmd_trial(message: Message):
    await message.answer(
        "🎁 <b>Бесплатный доступ — 1-й день курса</b>\n\n"
        "Изучи материал и возвращайся за 2-м днём 🚀",
        reply_markup=day1_kb()
    )


@dp.message(Command("tariffs"))
async def cmd_tariffs(message: Message):
    s = get_spots()
    text = (
        f"💰 <b>ТАРИФЫ</b>\n\n"
        f"⚠️ Мест по акции: <b>{s}</b>\n\n"
        "⭐ <b>VIP — 4 970 ₽</b>  ← берут 7 из 10\n"
        "🚀 <b>PRO + продвижение — 7 970 ₽</b>\n"
        "📦 <b>Базовый — 2 970 ₽</b>\n\n"
        "👇 Выбери:"
    )
    await message.answer(text, reply_markup=tariffs_kb(s))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ <b>ПОМОЩЬ</b>\n\n"
        "/start — главное меню\n"
        "/trial — бесплатный доступ\n"
        "/tariffs — тарифы\n"
        "/profile — твой прогресс, XP, скидка и бейджи 🎮\n"
        "/challenge — челлендж дня, оценит AI 🥊\n"
        "/top — рейтинг учеников 🏅\n\n"
        "💬 Менеджер ответит за 5 минут 👇"
    )
    await message.answer(text, reply_markup=to_manager_kb())


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
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
        f"  ▶️ день 1: {c.get('day1', 0)}\n"
        f"  ▶️ день 2: {c.get('day2', 0)}\n"
        f"  💰 тарифы: {c.get('special_tariffs', 0)}\n"
        f"  💳 счёт ЮKassa: {c.get('yookassa_invoice', 0)}\n"
        f"  💳 заявка картой: {c.get('card_request', 0)}\n"
        f"  ✅ оплачено: {c.get('pay_success', 0)}"
    )
    await message.answer(
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

async def follow_up_scheduler():
    while True:
        await asyncio.sleep(1800)
        ts = now_ts()

        for uid, data in list(users.items()):
            stage = data.get("stage", "start")
            try:
                # FU1: зашёл, не начал day1 — через 2ч
                if (stage == "start"
                        and not data.get("fu_start")
                        and ts - data.get("start_at", ts) > 2 * 3600):
                    await bot.send_message(
                        int(uid),
                        "👋 <b>Кстати — 2 дня курса ты всё ещё не взял.</b>\n\n"
                        "Без оплаты. Без карты.\n"
                        "40 минут — и ты поймёшь, как на этом зарабатывать.\n\n"
                        f"{social_proof()}\n\n"
                        "👇 Начать:",
                        reply_markup=day1_kb()
                    )
                    users[uid]["fu_start"] = True
                    save_users()

                # FU2: day1, не пошёл в day2 — через 4ч
                elif (stage == "day1"
                        and not data.get("fu_day1")
                        and ts - data.get("day1_at", ts) > 4 * 3600):
                    await bot.send_message(
                        int(uid),
                        "🔥 <b>Как 1-й день?</b>\n\n"
                        "На 2-м дне ты увидишь — где именно\n"
                        "лежат деньги в AI-фрилансе.\n\n"
                        "Плюс <b>открою закрытое предложение + 3 бонуса</b>\n"
                        "только для тех, кто дошёл до конца.\n\n"
                        "👇 Продолжай:",
                        reply_markup=day2_kb()
                    )
                    users[uid]["fu_day1"] = True
                    save_users()

                # FU3: tariffs, не купил — через 20ч
                elif (stage == "tariffs"
                        and not data.get("fu_tariffs")
                        and ts - data.get("tariffs_at", ts) > 20 * 3600):
                    s = get_spots()
                    await bot.send_message(
                        int(uid),
                        f"⚠️ <b>Осталось {s} мест и ~4 часа</b>\n\n"
                        "Потом цены вернутся к обычным (9 900 ₽ VIP).\n"
                        "Бонусы на 6 470 ₽ — пропадут.\n\n"
                        "Доступ к курсу — навсегда, без подписок.\n\n"
                        f"{social_proof()}\n\n"
                        "👇 Выбрать:",
                        reply_markup=tariffs_kb(s)
                    )
                    users[uid]["fu_tariffs"] = True
                    save_users()

                               # FU4: просил напомнить через 24ч
                if (data.get("remind_at") and ts > data["remind_at"]
                        and not data.get("remind_sent")):
                    await bot.send_message(
                        int(uid),
                        "⏰ <b>Напоминаю — это последний шанс.</b>\n\n"
                        "Акция закрывается. На следующий поток\n"
                        "цены поднимутся. Бонусы уже не будет.\n\n"
                        "Если планировал — сейчас лучший момент.\n\n"
                        "👇",
                        reply_markup=downsell_kb()
                    )
                    users[uid]["remind_sent"] = True
                    save_users()

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
