import asyncio
import json
import os
import logging
import random
import string
import time
import base64
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
WELCOME_IMG = "welcome.jpg"

STUDENTS_COUNT = "347"

# Цены: anchor (обычная) → текущая (акция)
PRICE_BASE = (5900, 2900)
PRICE_VIP = (9900, 4900)
PRICE_PRO = (14900, 7900)

logging.basicConfig(level=logging.INFO)

# Увеличенный таймаут для стабильной работы на Amvera (число секунд!)
_session = AiohttpSession(timeout=60)
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
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


promos = load_json(PROMO_FILE)
users = load_json(USERS_FILE)
spots_data = load_json(SPOTS_FILE, {"spots": 23, "updated": time.time()})


def save_promos(): save_json(PROMO_FILE, promos)
def save_users(): save_json(USERS_FILE, users)
def save_spots(): save_json(SPOTS_FILE, spots_data)


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

RECENT_BUYS = [
    "🔥 Анна из Москвы взяла VIP — 2 минуты назад",
    "🔥 Дмитрий из СПб оформил PRO — 7 минут назад",
    "🔥 Мария из Казани взяла VIP — 12 минут назад",
    "🔥 Сергей из Новосибирска взял VIP — 18 минут назад",
    "🔥 Ольга из Краснодара взяла PRO — 23 минуты назад",
    "🔥 Алексей из Екатеринбурга взял VIP — 31 минуту назад",
    "🔥 Юлия из Нижнего Новгорода взяла VIP — 42 минуты назад",
]


def social_proof() -> str:
    return random.choice(RECENT_BUYS)


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
        save_json(EVENTS_FILE, events_log)
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
    "homework":     "📝 Работа проверена AI",
}

XP_RULES = {
    "day1": 30, "day2": 50, "tariffs": 20,
    "free_gift": 15, "referral": 25, "daily": 10, "buy": 100,
    "homework": 40,
}

# ─── AI-НАСТАВНИК: проверка домашних работ ─────────────────────────────────────────────────────────
# Каскад провайдеров с бесплатными лимитами. Ключи ТОЛЬКО из окружения (никогда не хардкодим).
# Бот пробует провайдеров по очереди: упёрся в лимит/ошибку → автоматически следующий.
# Активируются только те, чей ключ задан в env. Все эндпоинты OpenAI-совместимые.
#
# Env-переменные ключей (добавляй любые — чем больше, тем устойчивее):
#   OPENROUTER_API_KEY  — openrouter.ai (много :free vision-моделей)
#   GROQ_API_KEY        — groq.com (быстрый бесплатный тир, Llama 4 vision)
#   GEMINI_API_KEY      — Google AI Studio (бесплатный тир, Gemini vision)
#   MISTRAL_API_KEY     — mistral.ai (бесплатный тир, Pixtral vision)
#   OPENAI_API_KEY      — OpenAI (платно, как последний резерв)

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")


def _build_providers():
    """Упорядоченный список попыток: сначала бесплатные тиры, платное — в конце."""
    p = []
    # 1) OpenRouter — несколько :free vision-моделей подряд (у каждой свой лимит)
    if OPENROUTER_KEY:
        for model in (
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free",
            "qwen/qwen2.5-vl-72b-instruct:free",
        ):
            p.append({
                "name": f"OpenRouter:{model}", "vision": True,
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "key": OPENROUTER_KEY,
                "model": model,
                "extra": {"HTTP-Referer": "https://t.me/Trueman_ai_bot", "X-Title": "True AI Academy"},
            })
    # 2) Google Gemini (бесплатный тир, vision)
    if GEMINI_KEY:
        p.append({
            "name": "Gemini:flash", "vision": True,
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "key": GEMINI_KEY, "model": "gemini-2.0-flash", "extra": {},
        })
    # 3) Groq (бесплатный тир, Llama 4 — vision)
    if GROQ_KEY:
        p.append({
            "name": "Groq:llama4", "vision": True,
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "key": GROQ_KEY, "model": "meta-llama/llama-4-scout-17b-16e-instruct", "extra": {},
        })
    # 4) Mistral (бесплатный тир, Pixtral — vision)
    if MISTRAL_KEY:
        p.append({
            "name": "Mistral:pixtral", "vision": True,
            "url": "https://api.mistral.ai/v1/chat/completions",
            "key": MISTRAL_KEY, "model": "pixtral-12b-2409", "extra": {},
        })
    # 5) OpenRouter платная резервная (если ключ есть)
    if OPENROUTER_KEY:
        p.append({
            "name": "OpenRouter:gpt-4o-mini", "vision": True,
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "key": OPENROUTER_KEY, "model": "openai/gpt-4o-mini",
            "extra": {"HTTP-Referer": "https://t.me/Trueman_ai_bot", "X-Title": "True AI Academy"},
        })
    # 6) OpenAI напрямую (платно, последний резерв)
    if OPENAI_KEY:
        p.append({
            "name": "OpenAI:gpt-4o-mini", "vision": True,
            "url": "https://api.openai.com/v1/chat/completions",
            "key": OPENAI_KEY, "model": "gpt-4o-mini", "extra": {},
        })
    return p


AI_PROVIDERS = _build_providers()

HW_SYSTEM_PROMPT = (
    "Ты — доброжелательный, но требовательный наставник курса по нейросетям "
    "True AI Academy. Ученик присылает свою домашнюю работу: изображение, кадр из "
    "AI-видео, карточку товара или текст/промпт, созданные с помощью нейросетей. "
    "Дай разбор на русском, кратко и по делу, строго в таком формате (с эмодзи-заголовками):\n\n"
    "✅ <b>Что получилось хорошо</b> — 2-3 пункта\n"
    "🛠 <b>Что улучшить</b> — 2-3 конкретных совета (композиция, свет, промпт, детали)\n"
    "⭐ <b>Оценка</b> — N/10\n"
    "👉 <b>Следующий шаг</b> — одно практическое задание\n\n"
    "Будь поддерживающим, мотивируй продолжать. Не используй markdown ** **, только "
    "HTML-теги <b></b>. Максимум ~180 слов."
)


async def _try_provider(prov, content) -> str:
    payload = {
        "model": prov["model"],
        "messages": [
            {"role": "system", "content": HW_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "max_tokens": 700,
        "temperature": 0.6,
    }
    headers = {"Authorization": f"Bearer {prov['key']}", "Content-Type": "application/json"}
    headers.update(prov.get("extra", {}))
    timeout = aiohttp.ClientTimeout(total=45)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(prov["url"], json=payload, headers=headers) as r:
            data = await r.json()
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {str(data)[:200]}")
            return data["choices"][0]["message"]["content"].strip()


async def ai_review(user_text: str, image_b64: str = None) -> str:
    """Перебирает провайдеров по очереди (бесплатные тиры → платные). None, если все недоступны."""
    if not AI_PROVIDERS:
        return None
    content = [{"type": "text", "text": user_text or "Проверь мою работу по курсу нейросетей."}]
    if image_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
        })
    for prov in AI_PROVIDERS:
        if image_b64 and not prov.get("vision"):
            continue
        try:
            result = await _try_provider(prov, content)
            if result:
                logging.info(f"AI review OK via {prov['name']}")
                return result
        except Exception as e:
            logging.warning(f"AI provider {prov['name']} failed: {e} → next")
            continue
    logging.error("AI review: all providers exhausted")
    return None


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
    return (
        f"🎮 <b>Профиль: {name}</b>\n\n"
        f"Уровень: <b>{lvl}</b>\n"
        f"Опыт: <b>{xp} XP</b>\n"
        f"{bar}\n"
        f"{nxt_line}\n\n"
        f"🔥 Серия дней подряд: <b>{u.get('streak', 0)}</b>\n\n"
        f"🏅 <b>Достижения ({len(badges)}/{len(BADGES)}):</b>\n{badges_str}\n\n"
        "💡 Заходи каждый день и проходи уроки — XP и бейджи копятся, "
        "а топ-ученики недели получают бонусы."
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
        "💡 XP даётся за уроки, серии дней и активность. "
        "Топ-3 в конце недели получают бонусные материалы."
    )


def badge_toast(badge_id: str) -> str:
    return f"\n\n🎉 <b>Новое достижение:</b> {BADGES.get(badge_id, badge_id)}  (+бейдж в профиль)"


class BroadcastState(StatesGroup):
    waiting = State()


class HomeworkState(StatesGroup):
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
        [
            InlineKeyboardButton(text="🎮 Мой прогресс", callback_data="profile"),
            InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard"),
        ],
        [InlineKeyboardButton(text="🤖 Сдать ДЗ — проверит AI-наставник", callback_data="homework")],
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
        [InlineKeyboardButton(text="✅ Готово — забрать ЗАКРЫТОЕ предложение 🎁", callback_data="special_tariffs")],
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
        payload = parts[1].strip()
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

    if is_new and os.path.exists(WELCOME_IMG):
        try:
            await message.answer_photo(
                photo=FSInputFile(WELCOME_IMG),
                caption=text,
                reply_markup=goal_kb()
            )
            return
        except Exception:
            pass
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

    text = (
        "🔐 <b>ЗАКРЫТОЕ ПРЕДЛОЖЕНИЕ — ПРОГРЕСС: ███ 100%</b>\n"
        "Ты прошёл 2 дня. Это видят единицы.\n\n"
        f"⏳ Сгорает до: <b>{deadline}</b> (24 часа)\n"
        f"⚠️ Мест по этой цене: <b>{s}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⭐ <b>VIP С КУРАТОРОМ</b>\n"
        "<s>9 900 ₽</s> → <b>4 970 ₽</b>  (экономия 4 930 ₽)\n"
        "это <b>16 ₽ в день</b> — дешевле чашки кофе\n\n"
        "Что внутри:\n"
        "✅ Все 7 дней курса + доступ навсегда\n"
        "✅ Личный куратор + проверка ДЗ\n"
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
        "✅ Личный куратор + проверка ДЗ\n"
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

    text = (
        f"✅ <b>Отличный выбор — {t['label']}!</b>\n\n"
        f"<s>{t['old']:,} ₽</s> → <b>{t['now']:,} ₽</b>\n".replace(",", " ") +
        f"{t['perks']}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💳 <b>Оплата картой РФ</b> — быстро и безопасно через ЮKassa,\n"
        "доступ открывается сразу после оплаты.\n\n"
        "🛡 Без риска: сначала 2 дня бесплатно, потом решаешь.\n"
        "💡 Есть промокод друга? Скидку 500 ₽ применит менеджер.\n\n"
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
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 <b>НОВАЯ ЗАЯВКА (карта)!</b>\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: <code>{call.from_user.id}</code>\n"
            f"📦 Тариф: {t['label']} — {t['now']} ₽\n"
            f"🎯 Цель: {goal}"
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
        [InlineKeyboardButton(text="🎓 Пройти урок (+XP)", callback_data="day1")],
        [InlineKeyboardButton(text="🏅 Рейтинг", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    await show(call, leaderboard_text(), InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Мой прогресс", callback_data="profile")],
        [InlineKeyboardButton(text="🎓 Заработать XP", callback_data="day1")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


# ─── AI-НАСТАВНИК: проверка ДЗ ─────────────────────────────────────────────────────────────────────

def homework_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="hw_cancel")],
    ])


@dp.callback_query(lambda c: c.data == "homework")
async def cb_homework(call: CallbackQuery, state: FSMContext):
    await state.set_state(HomeworkState.waiting)
    text = (
        "🤖 <b>AI-НАСТАВНИК — ПРОВЕРКА ДЗ</b>\n\n"
        "Пришли свою работу одним сообщением:\n"
        "🖼 <b>картинку</b> (изображение, карточка, кадр из видео)\n"
        "✍️ или <b>текст/промпт</b>, который ты составил.\n\n"
        "Я разберу: что получилось, что улучшить, оценю\n"
        "и подскажу следующий шаг. За проверку — <b>+40 XP</b> 🏅\n\n"
        "💡 К картинке можно добавить подпись — что ты хотел получить.\n\n"
        "👇 Жду твою работу:"
    )
    await show(call, text, homework_cancel_kb())


@dp.callback_query(lambda c: c.data == "hw_cancel")
async def cb_hw_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(call, "Окей, проверку отменил. Возвращайся, когда будешь готов 👇", start_kb())


@dp.message(HomeworkState.waiting)
async def process_homework(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    has_photo = bool(message.photo)
    user_text = (message.caption or message.text or "").strip()

    # Команда во время ожидания ДЗ — выходим из режима, не шлём в AI
    if not has_photo and user_text.startswith("/"):
        await state.clear()
        await message.answer("Окей, проверку отменил. Команда ниже 👇", reply_markup=start_kb())
        return

    if not has_photo and not user_text:
        await message.answer(
            "Пришли <b>картинку</b> или <b>текст</b> работы — и я её проверю 🙌",
            reply_markup=homework_cancel_kb(),
        )
        return

    await state.clear()
    thinking = await message.answer("🤖 Анализирую твою работу… это займёт несколько секунд.")

    image_b64 = None
    if has_photo:
        try:
            file = await bot.get_file(message.photo[-1].file_id)
            bio = await bot.download_file(file.file_path)
            image_b64 = base64.b64encode(bio.read()).decode("utf-8")
        except Exception as e:
            logging.error(f"HW download error: {e}")

    review = await ai_review(user_text, image_b64)

    try:
        await thinking.delete()
    except Exception:
        pass

    if not review:
        # Нет ключа AI или ошибка — мягкий fallback на куратора
        await message.answer(
            "🙌 <b>Работу получил!</b>\n\n"
            "Сейчас AI-проверка временно недоступна — твою работу\n"
            f"посмотрит живой куратор. Напиши ему: {MANAGER}\n\n"
            "А пока держи <b>+40 XP</b> за то, что сделал ДЗ 🏅",
            reply_markup=start_kb(),
        )
        add_xp(user_id, "homework")
        give_badge(user_id, "homework")
        track("homework_fallback", user_id)
        return

    track("homework_ai", user_id)
    add_xp(user_id, "homework")
    new_badge = give_badge(user_id, "homework")
    toast = badge_toast("homework") if new_badge else ""

    await message.answer(
        "🤖 <b>РАЗБОР ОТ AI-НАСТАВНИКА</b>\n\n"
        f"{review}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏅 <b>+40 XP</b> за выполненное ДЗ!" + toast,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Проверить ещё работу", callback_data="homework")],
            [InlineKeyboardButton(text="🎮 Мой прогресс", callback_data="profile")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
        ]),
    )
    try:
        name = message.from_user.first_name or "Юзер"
        await bot.send_message(
            ADMIN_ID,
            f"📝 <b>ДЗ проверено AI</b>\n"
            f"👤 {name} (<code>{user_id}</code>)\n"
            f"🖼 фото: {'да' if has_photo else 'нет'}"
        )
    except Exception:
        pass


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


@dp.message(Command("dz"))
async def cmd_dz(message: Message, state: FSMContext):
    await state.set_state(HomeworkState.waiting)
    await message.answer(
        "🤖 <b>AI-НАСТАВНИК — ПРОВЕРКА ДЗ</b>\n\n"
        "Пришли картинку или текст своей работы — разберу,\n"
        "оценю и подскажу, что улучшить. За проверку <b>+40 XP</b> 🏅",
        reply_markup=homework_cancel_kb(),
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
        "/profile — твой прогресс, XP и бейджи 🎮\n"
        "/dz — сдать домашку на проверку AI-наставнику 🤖\n"
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


# ─── ЗАПУСК с retry при сетевых сбоях ─────────────────────────────────────────────────────────

async def main():
    print("Бот запущен!")
    asyncio.create_task(follow_up_scheduler())

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
