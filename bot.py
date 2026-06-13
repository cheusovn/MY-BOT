import asyncio
import json
import os
import logging
import random
import string
import time
from datetime import datetime, timedelta
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
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

STUDENTS_COUNT = "2 347"

# Цены: anchor (обычная) → текущая (акция)
PRICE_BASE = (5900, 2900)
PRICE_VIP = (9900, 4900)
PRICE_PRO = (14900, 7900)

logging.basicConfig(level=logging.INFO)

# Увеличенные таймауты для стабильной работы на Amvera
_session = AiohttpSession(
    timeout=aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
)
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
        "<b>Честный факт:</b> 90% фрилансеров, кто освоил AI\n"
        "в этом году, вышли на <b>50–100k ₽/мес</b>.\n\n"
        "Остальные продолжают месяцами брать заказы по 1–2k.\n"
        "Разница — <b>один навык.</b>\n\n"
    ),
    "business": (
        "🏢 <b>Хочешь прокачать бизнес через AI?</b>\n\n"
        "<b>Правда:</b> твои конкуренты уже используют AI для\n"
        "контента, рекламы и продаж. Каждый месяц\n"
        "без этого — <b>это прямые потери.</b>\n\n"
        "Наши студенты-предприниматели:\n"
        "▸ Экономят 50–100k ₽/мес на подрядчиках\n"
        "▸ Получают в 3 раза больше контента\n"
        "▸ Поднимают продажи на 30–40%\n\n"
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


class BroadcastState(StatesGroup):
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
            InlineKeyboardButton(text="🛡 Гарантия", callback_data="guarantee"),
            InlineKeyboardButton(text="❓ Вопросы", callback_data="faq"),
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


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
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await call.answer()


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

    text = (
        f"👋 <b>{name}, привет!</b>\n\n"
        "Пока большинство ещё «думают попробовать» —\n"
        f"<b>{STUDENTS_COUNT}+ студентов</b> True AI Academy уже\n"
        "зарабатывают на нейросетях <b>30–100k ₽ в месяц</b>.\n\n"
        f"{social_proof()}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Без опыта\n"
        "✅ Без технических знаний\n"
        "✅ Первые 2 дня курса — бесплатно\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>Что тебе важнее?</b>\n"
        "Выбери — покажу нужный путь:"
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

    text = (
        "🎓 <b>ДЕНЬ 1 — ПРОГРЕСС: █░░ 33%</b>\n\n"
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
    )
    await show(call, text, day1_kb())


@dp.callback_query(lambda c: c.data == "day2")
async def cb_day2(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "day2")

    text = (
        "🔥 <b>ДЕНЬ 2 — ПРОГРЕСС: ██░ 66%</b>\n\n"
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
    )
    await show(call, text, day2_kb())


@dp.callback_query(lambda c: c.data == "special_tariffs")
async def cb_special_tariffs(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "tariffs")
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
        "🛡 <b>Двойная гарантия:</b>\n"
        "Не понравится 1-й день — вернём <b>100% + 500 ₽</b>\n"
        "за потраченное время. Без вопросов.\n\n"
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
        "🛡 <b>Двойная гарантия:</b>\n"
        "Не понравится 1-й день — <b>100% + 500 ₽</b> за время.\n\n"
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
        "💬 <b>Дмитрий, бизнес → Экономия 50k/мес:</b>\n"
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
        "❔ <b>Когда реально заработаю?</b>\n"
        "Первые заказы — на 3–7 день.\n"
        "Стабильный доход 30–80k — через 2–4 недели.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>А вдруг не получится?</b>\n"
        "Риска нет. 2 дня бесплатно — проверь.\n"
        "+ Двойная гарантия: 100% + 500₽ компенсации.\n\n"
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
        "🛡 <b>ДВОЙНАЯ ГАРАНТИЯ ВОЗВРАТА</b>\n\n"
        "Ты рискуешь <b>МЕНЬШЕ, ЧЕМ МЫ.</b>\n\n"
        "▸ Пройди <b>1-й день</b> полного курса\n"
        "▸ Если не понравилось — напиши менеджеру\n"
        "▸ Вернём <b>100% оплаты</b>\n"
        "▸ + Доплатим <b>500 ₽</b> за потраченное время\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Почему мы можем себе такое позволить?</b>\n\n"
        f"Из <b>{STUDENTS_COUNT}+ студентов</b> возвратов\n"
        "было <b>0,3%</b>. Курс реально работает.\n\n"
        "💬 <i>«Гарантия помогла решиться.\n"
        "Возврат не понадобился» — Ольга</i>"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Ок, беру VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="← К тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    plans = {
        "buy_base": ("📦 Базовый — 2 970 ₽", "Базовый", "base"),
        "buy_vip":  ("⭐ VIP — 4 970 ₽", "VIP", "vip"),
        "buy_pro":  ("🚀 PRO — 7 970 ₽", "PRO", "pro"),
    }
    plan_label, plan_short, plan_key = plans.get(call.data, ("Тариф", "—", "vip"))
    user_id = str(call.from_user.id)
    set_stage(user_id, "purchased")

    text = (
        f"✅ <b>Отличный выбор — {plan_short}!</b>\n\n"
        "🎯 <b>Что сейчас произойдёт:</b>\n"
        "1️⃣ Напиши менеджеру\n"
        "2️⃣ Он пришлёт реквизиты (сбер/тинькофф/карта)\n"
        "3️⃣ Оплата за 2 минуты\n"
        "4️⃣ Доступ + бонусы приходят сразу\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 <b>ПРОМОКОД ДРУГА?</b>\n"
        "Назови его менеджеру — <b>скидка 500 ₽</b>.\n\n"
        "✨ <b>UPGRADE за +990 ₽:</b>\n"
        "Личный созвон с куратором 60 мин.\n"
        "Разбор твоей ситуации, первые шаги.\n"
        "(обычно 4 900 ₽ — сейчас 990 ₽ к тарифу)\n\n"
        "🛡 Двойная гарантия возврата действует.\n\n"
        "👇 Написать менеджеру:"
    )
    await show(call, text, to_manager_with_bump_kb(plan_key))

    name = call.from_user.first_name or "Юзер"
    uname = f"@{call.from_user.username}" if call.from_user.username else "нет username"
    goal = GOAL_LABELS.get(users.get(user_id, {}).get("goal", ""), "—")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 <b>НОВАЯ ЗАЯВКА!</b>\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: <code>{call.from_user.id}</code>\n"
            f"📦 Тариф: {plan_label}\n"
            f"🎯 Цель: {goal}"
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


# ─── КОМАНДЫ ───────────────────────────────────────────────────────────────────────────

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
        "/tariffs — тарифы\n\n"
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
    purchased = stages.get("purchased", 0)
    conv = (purchased / total * 100) if total else 0
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{total}</b>\n"
        f"💰 Заявок: <b>{purchased}</b> ({conv:.1f}%)\n"
        f"🎫 Промокодов: <b>{len(promos)}</b>\n"
        f"📦 Мест осталось: <b>{get_spots()}</b>\n\n"
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
                        "Риска нет: двойная гарантия 100% + 500₽.\n\n"
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
