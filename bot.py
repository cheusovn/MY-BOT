import asyncio
import html
import json
import os
import logging
import random
import re
import string
import time
import base64
import uuid
import aiohttp
from urllib.parse import quote
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile,
    BufferedInputFile, LabeledPrice, PreCheckoutQuery, ErrorEvent, BotCommand,
)
from aiogram.exceptions import (
    TelegramNetworkError, TelegramRetryAfter, TelegramBadRequest,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

BOT_TOKEN = os.environ.get("BOT_TOKEN")
# ADMIN_ID берётся из env (ADMIN_ID), default — исторический ID владельца.
# Поддерживается список через запятую: "111,222,333" (полезно при передаче бота).
_ADMIN_ENV = os.environ.get("ADMIN_ID", "817730727").strip()
try:
    ADMIN_IDS = {int(x) for x in _ADMIN_ENV.replace(";", ",").split(",") if x.strip()}
except ValueError:
    ADMIN_IDS = {817730727}
# Обратная совместимость с одиночным ADMIN_ID по всему коду
ADMIN_ID = next(iter(ADMIN_IDS)) if ADMIN_IDS else 817730727


def is_admin(uid) -> bool:
    """Владелец-админ — для полного теста бота без лимитов (время, генерации, гейты).
    На обычных пользователей не влияет."""
    try:
        return int(uid) in ADMIN_IDS
    except (TypeError, ValueError):
        return False


def esc(s) -> str:
    """HTML-escape для подстановки имён/username в сообщения с parse_mode=HTML.
    Без этого юзер с first_name='<a href="evil">x</a>' ломает разметку и
    подсовывает кликабельные ссылки в админ-уведомления."""
    return html.escape(str(s or ""), quote=False)
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

# ─── Реферальный баланс (₽) ─────────────────────────────────────────────────
REF_PERCENT = 30        # % с оплаты приглашённого друга → на баланс пригласившего
REF_MIN_PAYOUT = 2000   # минимальная сумма вывода на карту, ₽
REF_TO_XP_RATE = 1      # 1 ₽ реферального баланса = N XP при переводе в XP
WELCOME_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.jpg")
# Брендовые шапки-баннеры экранов (генерируются scripts/make_banners.py)
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

STUDENTS_COUNT = "347"

# 2-й день курса открывается только спустя это время после старта 1-го дня
# (даём материалу «улечься» — лучше усваивается, выше доходимость).
DAY2_COOLDOWN = 12 * 3600  # секунд

logging.basicConfig(level=logging.INFO)

# ─── Sentry (опционально) ─────────────────────────────────────────────────────
# Активируется только при наличии SENTRY_DSN. Без env — no-op, нулевой оверхед.
if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=os.environ["SENTRY_DSN"],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0.0")),
            send_default_pii=False,  # не отправляем PII в Sentry
        )
        logging.info("Sentry initialized")
    except Exception as _e:
        logging.warning(f"Sentry init failed: {_e}")

# ─── Глобальная aiohttp-сессия для всех внешних вызовов (OpenRouter / YooKassa) ─
# Раньше создавалась новая сессия на каждый запрос (TCP+DNS overhead ~сотни мс,
# на медленном линке хуже). Делаем одну общую с пулом коннекшнов и DNS-кэшем.
_HTTP_SESSION: aiohttp.ClientSession | None = None
_HTTP_SESSION_LOCK = asyncio.Lock()


async def get_http() -> aiohttp.ClientSession:
    """Ленивая инициализация общей aiohttp.ClientSession.
    Создаётся при первом вызове внутри уже работающего event loop."""
    global _HTTP_SESSION
    if _HTTP_SESSION is None or _HTTP_SESSION.closed:
        async with _HTTP_SESSION_LOCK:
            if _HTTP_SESSION is None or _HTTP_SESSION.closed:
                _HTTP_SESSION = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(
                        limit=100, ttl_dns_cache=300, family=0,
                    ),
                    timeout=aiohttp.ClientTimeout(total=120),
                )
    return _HTTP_SESSION


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
# FSM-хранилище: Redis (если задан REDIS_URL), иначе Memory.
# При MemoryStorage любой рестарт обрывает PayState/WowState/BroadcastState —
# юзер посреди оплаты теряет сессию. Redis это лечит.
def _build_storage():
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        return MemoryStorage()
    try:
        from aiogram.fsm.storage.redis import RedisStorage
        logging.info(f"FSM: RedisStorage via {redis_url.split('@')[-1]}")
        return RedisStorage.from_url(redis_url)
    except Exception as _e:
        logging.warning(f"Redis storage init failed ({_e}) → MemoryStorage fallback")
        return MemoryStorage()


dp = Dispatcher(storage=_build_storage())


# ─── Анти-дабл-тап на кнопках ───────────────────────────────────────────────
# При лаге Telegram копит нажатия и потом выполняет колбэки пачкой → открывалось
# по 3-4 экрана. Гасим: повтор той же кнопки в окне DEBOUNCE и параллельные
# нажатия от одного юзера игнорируем (только подтверждаем callback, чтобы убрать «часики»).
_CB_DEBOUNCE = 2.5          # сек: окно подавления повторов одной и той же кнопки
_cb_last: dict = {}         # (uid, data) -> ts последнего принятого нажатия
_cb_inflight: set = set()   # uid, у которых колбэк сейчас обрабатывается


class AntiDoubleTap(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = event.from_user.id if event.from_user else 0
        now = time.time()
        key = (uid, event.data)
        # 1) тот же колбэк недавно уже приняли — это дабл/тройной тап
        if now - _cb_last.get(key, 0) < _CB_DEBOUNCE:
            try:
                await event.answer()
            except Exception:
                pass
            return
        # 2) для этого юзера колбэк уже в обработке — параллельные дропаем
        if uid in _cb_inflight:
            try:
                await event.answer()
            except Exception:
                pass
            return
        _cb_last[key] = now
        if len(_cb_last) > 4000:          # лёгкая чистка, чтобы не рос бесконечно
            cutoff = now - 60
            for k in [k for k, t in _cb_last.items() if t < cutoff]:
                _cb_last.pop(k, None)
        _cb_inflight.add(uid)
        try:
            return await handler(event, data)
        finally:
            _cb_inflight.discard(uid)


dp.callback_query.middleware(AntiDoubleTap())

# ─── Анти-повтор тяжёлых операций (генерация, /imgtest) ─────────────────────
# Команда/сообщение, запускающее долгую AI-операцию, не должно стартовать второй
# раз, пока первая ещё идёт (при лаге юзер жмёт 2-3 раза → генерировалось 4 раза).
_busy_users: set = set()


def single_flight(fn):
    """Декоратор для message-хендлеров: один тяжёлый запрос на пользователя за раз."""
    async def wrapper(message, *a, **k):
        uid = message.from_user.id if message.from_user else 0
        if uid in _busy_users:
            try:
                await message.answer("⏳ Уже выполняю предыдущий запрос — дождись результата 🙂")
            except Exception:
                pass
            return
        _busy_users.add(uid)
        try:
            return await fn(message, *a, **k)
        finally:
            _busy_users.discard(uid)
    wrapper.__wrapped__ = fn
    wrapper.__name__ = getattr(fn, "__name__", "wrapper")
    wrapper.__doc__ = getattr(fn, "__doc__", None)
    return wrapper


@dp.errors()
async def on_error(event: ErrorEvent):
    """Глобальный перехват ошибок: сетевые сбои Telegram логируем одной строкой
    (бот сам переподключается через polling), остальное — с трейсбеком."""
    exc = event.exception
    if isinstance(exc, (TelegramNetworkError, TelegramRetryAfter)):
        logging.warning(f"Сетевой сбой Telegram (восстановится сам): {type(exc).__name__}: {exc}")
    else:
        logging.exception(f"Необработанная ошибка: {type(exc).__name__}: {exc}")
    return True  # считаем обработанной — не роняем polling


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
    # Атомарная запись: пишем во временный файл и подменяем, чтобы не оставить битый JSON.
    # Защита от RuntimeError: dictionary changed size during iteration — копируем структуру
    # перед сериализацией (модификации из других корутин не уронят json.dump).
    try:
        snapshot = json.loads(json.dumps(data, ensure_ascii=False))
    except Exception:
        snapshot = data
    tmp = f"{file}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
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


# ─── УЧЁТ РАСХОДОВ НА ГЕНЕРАЦИЮ (OpenRouter) ────────────────────────────────────────────────────────
USD_RUB = 100  # курс для подсчёта расходов в ₽ (1 $ = 100 ₽)
# Цена за 1 картинку, $. Измерено по Activity: 2.5 и 3.1. Остальные — оценка (≈).
GEN_COST_USD = {
    "google/gemini-2.5-flash-image":         0.039,
    "google/gemini-3.1-flash-image-preview": 0.068,
    "google/gemini-3-pro-image-preview":     0.12,
    "openai/gpt-5-image-mini":               0.05,
    "openai/gpt-5-image":                    0.15,
    "openai/gpt-5.4-image-2":                0.20,
    "sourceful/riverflow-v2-fast":           0.02,
    "bytedance-seed/seedream-4.5":           0.04,
    "black-forest-labs/flux.2-pro":          0.045,
    "x-ai/grok-imagine-image-quality":       0.06,
}
# Цены по факту OpenRouter (остальные — оценка ≈)
GEN_COST_MEASURED = {
    "google/gemini-2.5-flash-image", "google/gemini-3.1-flash-image-preview",
    "sourceful/riverflow-v2-fast", "bytedance-seed/seedream-4.5",
}
GEN_LABELS = {
    "google/gemini-2.5-flash-image":         "Nano Banana (2.5)",
    "google/gemini-3.1-flash-image-preview": "Nano Banana 2 (3.1)",
    "google/gemini-3-pro-image-preview":     "Nano Banana Pro",
    "openai/gpt-5-image-mini":               "GPT Image mini",
    "openai/gpt-5-image":                    "GPT Image",
    "openai/gpt-5.4-image-2":                "GPT Image Pro (5.4)",
    "sourceful/riverflow-v2-fast":           "Riverflow Fast",
    "bytedance-seed/seedream-4.5":           "Seedream 4.5",
    "black-forest-labs/flux.2-pro":          "FLUX.2 Pro",
    "x-ai/grok-imagine-image-quality":       "Grok Imagine",
}


def record_gen(model_id: str):
    """Считает успешные генерации по модели (для раздела «Расходы» в админке)."""
    try:
        gc = events_log.setdefault("gen_counts", {})
        gc[model_id] = gc.get(model_id, 0) + 1
        _mark_dirty("events")
    except Exception:
        pass


def build_spend_text() -> str:
    gc = events_log.get("gen_counts", {})
    lines, total_usd = [], 0.0
    for mid, label in GEN_LABELS.items():
        n = gc.get(mid, 0)
        unit = GEN_COST_USD.get(mid, 0.0)
        sub = n * unit
        total_usd += sub
        mark = "" if mid in GEN_COST_MEASURED else "≈"
        lines.append(
            f"• {label}: <b>{n}</b> × {mark}${unit:.3f} = ${sub:.2f} ({sub * USD_RUB:.0f} ₽)"
        )
    # неизвестные модели, если вдруг появятся
    for mid, n in gc.items():
        if mid not in GEN_LABELS:
            lines.append(f"• {mid}: <b>{n}</b> (цена неизв.)")
    total_n = sum(gc.values())
    return (
        f"💸 <b>Расходы на генерацию</b>\n"
        f"<i>Курс: 1 $ = {USD_RUB} ₽ · ≈ — оценка, без ≈ — по факту OpenRouter</i>\n\n"
        f"{chr(10).join(lines) if lines else '— генераций пока не было'}\n\n"
        f"🖼 Всего генераций: <b>{total_n}</b>\n"
        f"💰 <b>Итого: ${total_usd:.2f} ≈ {total_usd * USD_RUB:.0f} ₽</b>"
    )


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
    "challenge": 10, "wow": 5, "ref_join": 10,
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
