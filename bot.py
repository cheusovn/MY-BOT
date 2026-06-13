import asyncio
import json
import os
import logging
import random
import string
import time
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 817730727
BOT_USERNAME = "Trueman_ai_bot"
TRIAL_DAY_1 = "https://t.me/+5ep9DPf7eNMzZjdi"
TRIAL_DAY_2 = "https://t.me/+SpoNR-ahkJFiZTJi"
GIFT_LINK = "https://t.me/syntxaibot?start=aff_817730727"
MANAGER = "@nikolay_cheusov"
WELCOME_IMG = "welcome.jpg"

STUDENTS_COUNT = "2 347"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
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


GOAL_LABELS = {
    "freelance": "заработок на фрилансе",
    "business": "прокачку бизнеса",
    "curious": "знакомство с AI",
}

GOAL_HOOKS = {
    "freelance": (
        "💸 <b>Хочешь зарабатывать на нейросетях?</b>\n\n"
        "Правильный выбор. Фриланс на AI — один из\n"
        "самых быстрорастущих рынков прямо сейчас.\n\n"
        "Студенты академии берут первые заказы\n"
        "уже на <b>3–7 день курса.</b>\n"
        "Логотипы, иллюстрации, контент — <b>5–30k ₽ за проект.</b>\n\n"
    ),
    "business": (
        "🏢 <b>Хочешь прокачать бизнес через AI?</b>\n\n"
        "Контент, реклама, дизайн — нейросети\n"
        "делают всё это <b>в 10 раз быстрее и дешевле.</b>\n\n"
        "Студенты экономят <b>30–80 000 ₽/мес</b>\n"
        "на подрядчиках, не снижая качество.\n\n"
    ),
    "curious": (
        "🔍 <b>Хочешь разобраться в нейросетях?</b>\n\n"
        "Отличный старт. Это проще, чем кажется —\n"
        "никаких технических знаний не нужно.\n\n"
        "Начнёшь с нуля и за 2 дня поймёшь,\n"
        "<b>как это работает и где деньги.</b>\n\n"
    ),
}


class BroadcastState(StatesGroup):
    waiting = State()


# ─── КЛАВИАТУРЫ ───────────────────────────────────────────────────────────────

def goal_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Хочу зарабатывать удалённо", callback_data="goal_freelance")],
        [InlineKeyboardButton(text="🏢 Хочу прокачать свой бизнес", callback_data="goal_business")],
        [InlineKeyboardButton(text="🔍 Хочу разобраться что такое AI", callback_data="goal_curious")],
    ])


def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Попробовать курс — 2 дня БЕСПЛАТНО", callback_data="day1")],
        [InlineKeyboardButton(text="🔥 Подарок — 100+ нейросетей бесплатно", callback_data="free_gift")],
        [
            InlineKeyboardButton(text="💰 Тарифы", callback_data="tariffs"),
            InlineKeyboardButton(text="🏆 Результаты", callback_data="results"),
        ],
        [InlineKeyboardButton(text="💸 Зарабатывай с друзьями", callback_data="referral")],
    ])


def free_gift_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 ЗАБРАТЬ БЕСПЛАТНО ПРЯМО СЕЙЧАС", url=GIFT_LINK)],
        [InlineKeyboardButton(text="🎓 Также попробовать курс (2 дня бесплатно)", callback_data="day1")],
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
    s = spots if spots is not None else get_spots()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ VIP с куратором — 4 900 ₽  ← берут 7 из 10", callback_data="buy_vip")],
        [InlineKeyboardButton(text="🚀 PRO + продвижение — 7 900 ₽", callback_data="buy_pro")],
        [InlineKeyboardButton(text="📦 Базовый — 2 900 ₽", callback_data="buy_base")],
        [
            InlineKeyboardButton(text="🛡 Гарантия", callback_data="guarantee"),
            InlineKeyboardButton(text="❓ Вопросы", callback_data="faq"),
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def to_manager_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру — отвечает за 5 мин", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


# ─── ВСПОМОГАТЕЛЬНАЯ ──────────────────────────────────────────────────────────

async def show(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await call.answer()


# ─── ХЭНДЛЕРЫ ─────────────────────────────────────────────────────────────────

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
        "Нейросети уже меняют рынок труда.\n"
        "Те, кто освоил их сейчас — <b>зарабатывают удалённо\n"
        "от 30 000 ₽ в месяц</b>, работая из любой точки мира.\n\n"
        f"В <b>True AI Academy</b> уже <b>{STUDENTS_COUNT}+ студентов.</b>\n"
        "Без опыта. Без технических знаний. С нуля.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❓ <b>Для чего тебе нейросети?</b>\n"
        "Выбери — подберём лучший путь:"
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
        "🎓 <b>Начни прямо сейчас — бесплатно:</b>\n\n"
        "👇 Выбери, с чего начнём:"
    )
    await show(call, text, start_kb())


@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    name = call.from_user.first_name or "друг"
    text = (
        f"🏠 <b>Главное меню</b>\n\n"
        f"{name}, что выбираешь? 👇"
    )
    await show(call, text, start_kb())


@dp.callback_query(lambda c: c.data == "free_gift")
async def cb_free_gift(call: CallbackQuery):
    text = (
        "🎁 <b>100+ НЕЙРОСЕТЕЙ — БЕСПЛАТНО НА 100+ ДНЕЙ</b>\n\n"
        "Прямо сейчас получаешь доступ к лучшим\n"
        "нейросетям мира — <b>без карты и оплаты.</b>\n\n"
        "<b>Что входит:</b>\n"
        "🎨 Midjourney — изображения уровня рекламных студий\n"
        "🎬 Kling, Runway, Veo — AI-видео за минуты\n"
        "🤖 ChatGPT Plus — тексты, идеи, сценарии\n"
        "🎵 Suno — музыка и саундтреки\n"
        "🔊 ElevenLabs — реалистичная озвучка\n"
        "📸 Nano Banana — фото и визуалы\n"
        "и ещё <b>95+ инструментов</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⚡ Это не триал на 3 дня.\n"
        "Это <b>100+ дней</b> полноценного доступа.\n\n"
        f"🔥 Уже <b>{STUDENTS_COUNT}+ человек</b> забрали подарок.\n"
        "👇 Нажми и получи прямо сейчас:"
    )
    await show(call, text, free_gift_kb())


@dp.callback_query(lambda c: c.data == "day1")
async def cb_day1(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "day1")

    text = (
        "🎓 <b>День 1 — Твой первый шаг в мир AI</b>\n\n"
        "┌─────────────────────────────┐\n"
        "│  📅  ДЕНЬ 1 — ПОГРУЖЕНИЕ      │\n"
        "└─────────────────────────────┘\n\n"
        "<b>Что сделаешь за 40 минут:</b>\n"
        "▸ Запустишь нейросеть — без регистраций и знаний\n"
        "▸ Создашь изображения, которые удивят окружающих\n"
        "▸ Напишешь первый промпт, который реально работает\n"
        "▸ Узнаешь, <i>где именно деньги в AI-фрилансе</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <i>«После 1-го дня понял: это не сложно.\n"
        "Просто раньше боялся начать»</i>\n"
        "<b>— Алексей, студент</b>\n\n"
        "👇 Открывай прямо сейчас:"
    )
    await show(call, text, day1_kb())


@dp.callback_query(lambda c: c.data == "day2")
async def cb_day2(call: CallbackQuery):
    user_id = str(call.from_user.id)
    set_stage(user_id, "day2")

    text = (
        "🔥 <b>День 1 пройден! Ты уже не новичок.</b>\n\n"
        "┌─────────────────────────────┐\n"
        "│  📅  ДЕНЬ 2 — ПРОКАЧКА        │\n"
        "└─────────────────────────────┘\n\n"
        "Сегодня пересечёшь черту между\n"
        "«просто интересно» и <b>«могу зарабатывать».</b>\n\n"
        "<b>Что сделаешь сегодня:</b>\n"
        "▸ Профессиональные генерации — уровень эксперта\n"
        "▸ Промпты без шаблонов — твой персональный стиль\n"
        "▸ Создашь работы, за которые <b>платят 5–30k ₽</b>\n"
        "▸ Увидишь воронку: навык → заказ → деньги\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <i>«После 2-го дня взял первый заказ на 8 000 ₽.\n"
        "Не верил, что так быстро получится»</i>\n"
        "<b>— Марина, 3 недели обучения</b>\n\n"
        "⚡ После 2-го дня — <b>закрытое предложение</b>\n"
        "только для тех, кто дошёл до конца.\n\n"
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

    text = (
        "🔐 <b>ЗАКРЫТОЕ ПРЕДЛОЖЕНИЕ</b>\n"
        "Только для тех, кто прошёл оба дня обучения\n\n"
        "⏳ <b>Это предложение действует 24 часа</b>\n"
        f"⚠️ Осталось мест по этой цене: <b>{s}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "Ты только что <b>своими руками</b> убедился — это работает.\n"
        "Теперь реши, как далеко идёшь.\n\n"
        "⭐ <b>VIP С КУРАТОРОМ — 4 900 ₽</b>  ← берут 7 из 10\n"
        "Все 7 дней + личный куратор + проверка ДЗ\n"
        "Закрытый чат 24/7. Доступ навсегда.\n\n"
        "🚀 <b>PRO + ПРОДВИЖЕНИЕ — 7 900 ₽</b>\n"
        "Всё из VIP + где брать заказы, SMM, реклама,\n"
        "вирусный контент, как набрать 1 млн просмотров\n\n"
        "📦 <b>БАЗОВЫЙ — 2 900 ₽</b>\n"
        "Все 7 дней, доступ навсегда, в своём темпе\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🛡 Не понравится 1-й день полного курса — <b>вернём деньги.</b>\n"
        "Без вопросов и условий.\n\n"
        "👇 Выбирай — менеджер ответит за 5 минут:"
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
        f"⚠️ Осталось мест по акционной цене: <b>{s}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "⭐ <b>VIP С КУРАТОРОМ — 4 900 ₽</b>  ← берут 7 из 10\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Все 7 дней курса\n"
        "✅ Личный куратор + проверка домашних заданий\n"
        "✅ Закрытый чат поддержки 24/7\n"
        "✅ Доступ навсегда\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🚀 <b>PRO + ПРОДВИЖЕНИЕ — 7 900 ₽</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Всё из VIP\n"
        "💼 Где брать заказы — проверенные площадки\n"
        "🔥 Вирусный контент (что залетает)\n"
        "📢 Реклама без слива бюджета\n"
        "📱 SMM-маркетинг с нуля\n"
        "🎯 Как набрать 1 млн просмотров\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📦 <b>БАЗОВЫЙ — 2 900 ₽</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ Все 7 дней курса\n"
        "✅ Доступ навсегда\n\n"
        "🛡 Гарантия: не понравится 1-й день — вернём деньги.\n\n"
        "👇 Выбирай тариф:"
    )
    await show(call, text, tariffs_kb(s))


@dp.callback_query(lambda c: c.data == "results")
async def cb_results(call: CallbackQuery):
    text = (
        "🏆 <b>РЕЗУЛЬТАТЫ СТУДЕНТОВ</b>\n\n"
        f"За полгода через академию прошли <b>{STUDENTS_COUNT}+ человек.</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Марина, фрилансер:</b>\n"
        "<i>«Взяла первый заказ через 3 дня после курса.\n"
        "8 000 ₽ за генерацию логотипов. В шоке, что так просто»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Алексей, менеджер:</b>\n"
        "<i>«Не технарь совсем. Оказалось,\n"
        "нейросети проще, чем Excel. +30k/мес»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Ирина, работает из дома:</b>\n"
        "<i>«Нашла 4 заказчика на иллюстрации.\n"
        "Зарабатываю 25–40k ₽ в месяц»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💬 <b>Дмитрий, бизнес:</b>\n"
        "<i>«Весь контент делаю сам.\n"
        "Экономлю 50 000 ₽/мес на дизайнерах»</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎓 <b>Начни бесплатно — и убедись сам</b>"
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
        "❔ <b>Нужны технические знания?</b>\n"
        "Нет. Если умеешь пользоваться смартфоном — разберёшься.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Когда реально заработать?</b>\n"
        "Первые заказы студенты берут на 3–7 день.\n"
        "Стабильный доход 30–80k ₽/мес — через 2–4 недели практики.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>А вдруг не получится?</b>\n"
        "Поэтому даём 2 дня бесплатно — проверь сам.\n"
        "Плюс гарантия возврата после 1-го дня курса.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Когда начинается обучение?</b>\n"
        "Сразу после оплаты. Доступ 24/7, в своём темпе.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "❔ <b>Сколько времени нужно в день?</b>\n"
        "1–2 часа достаточно. Заточен под занятых людей.\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Остались вопросы? 👇"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="← Назад к тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "guarantee")
async def cb_guarantee(call: CallbackQuery):
    text = (
        "🛡 <b>ГАРАНТИЯ ВОЗВРАТА ДЕНЕГ</b>\n\n"
        "Мы уверены в качестве курса.\n\n"
        "▸ Пройди <b>1-й день</b> полного курса\n"
        "▸ Если не понравилось — напиши менеджеру\n"
        "▸ Вернём <b>100% оплаты</b> — без вопросов\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"Из <b>{STUDENTS_COUNT}+ студентов</b> возвратов\n"
        "было единицы. Курс реально работает.\n\n"
        "💬 <i>«Гарантия помогла решиться. Возврат не понадобился»\n"
        "— Ольга, студентка</i>"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад к тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    plans = {
        "buy_base": ("📦 Базовый — 2 900 ₽", "Базовый"),
        "buy_vip":  ("⭐ VIP с куратором — 4 900 ₽", "VIP"),
        "buy_pro":  ("🚀 PRO + продвижение — 7 900 ₽", "PRO"),
    }
    plan_label, plan_short = plans.get(call.data, ("Тариф", "выбранный"))
    user_id = str(call.from_user.id)
    set_stage(user_id, "purchased")

    text = (
        f"✅ <b>Отличный выбор — тариф {plan_short}!</b>\n\n"
        "Напиши менеджеру — он пришлёт реквизиты\n"
        "и откроет доступ в течение нескольких минут. 🚀\n\n"
        "💡 <b>Есть промокод друга?</b>\n"
        "Назови его менеджеру — получишь <b>скидку 500 ₽</b>.\n\n"
        "🛡 Гарантия возврата действует\n"
        "после 1-го дня полного курса.\n\n"
        "👇 Написать прямо сейчас:"
    )
    await show(call, text, to_manager_kb())

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


@dp.callback_query(lambda c: c.data == "referral")
async def cb_referral(call: CallbackQuery):
    user_id = str(call.from_user.id)
    name = call.from_user.first_name or "друг"

    # Auto-generate code if user doesn't have one
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
                f"🎫 <b>Новый промокод</b>\n\n"
                f"👤 {name}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"🎫 Промокод: <code>{code}</code>"
            )
        except Exception:
            pass

    text = (
        "👥 <b>ПАРТНЁРСКАЯ ПРОГРАММА</b>\n\n"
        "🎁 Ты получаешь <b>30% с каждой оплаты друга</b> — на карту\n"
        "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
        f"🎫 <b>Твой промокод:</b> <code>{code}</code>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Как зарабатывать:</b>\n"
        "1️⃣ Поделись промокодом с другом\n"
        "2️⃣ Друг называет его менеджеру при оплате\n"
        "3️⃣ 30% зачисляется на карту 💸\n\n"
        "💡 <i>Пример: 3 друга купили VIP (4 900₽) →\n"
        "ты получаешь 4 410 ₽ на карту</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>Готовый текст для друга:</b>\n\n"
        f"<i>Привет! Учусь в True AI Academy — нейросети и заработок.\n"
        f"Первые 2 дня бесплатно: @{BOT_USERNAME}\n"
        f"Промокод при оплате: {code} — скидка 500₽</i>"
    )
    await show(call, text, back_kb())


# ─── КОМАНДЫ ──────────────────────────────────────────────────────────────────

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
        f"💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n\n"
        f"⚠️ Осталось мест по акционной цене: <b>{s}</b>\n\n"
        "⭐ <b>VIP с куратором — 4 900 ₽</b>  ← берут 7 из 10\n"
        "🚀 <b>PRO + продвижение — 7 900 ₽</b>\n"
        "📦 <b>Базовый — 2 900 ₽</b>\n\n"
        "👇 Выбери свой тариф:"
    )
    await message.answer(text, reply_markup=tariffs_kb(s))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ <b>ПОМОЩЬ И ПОДДЕРЖКА</b>\n\n"
        "<b>Команды:</b>\n"
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
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{len(users)}</b>\n"
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
        f"📢 <b>Рассылка</b>\n\n"
        f"Будет отправлено <b>{len(users)}</b> пользователям.\n\n"
        "Напиши текст сообщения (HTML работает).\n"
        "Для отмены: /cancel"
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
    await message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"Отправлено: <b>{sent}</b>\n"
        f"Не доставлено: <b>{failed}</b>"
    )


@dp.message(Command("promo"))
async def cmd_promo_check(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Формат: <code>/promo КОД</code>")
        return
    code = args[1].upper()
    owner = promos.get(code)
    if owner:
        owner_name = users.get(owner, {}).get("name", "—")
        await message.answer(
            f"🎫 Промокод <b>{code}</b>\n"
            f"👤 Владелец: {owner_name}\n"
            f"🆔 ID: <code>{owner}</code>"
        )
    else:
        await message.answer(f"❌ Промокод <b>{code}</b> не найден.")


# ─── ФОНОВЫЕ ЗАДАЧИ (FOLLOW-UP ЦЕПОЧКА) ──────────────────────────────────────

async def follow_up_scheduler():
    """Автоматические follow-up сообщения по стадиям воронки."""
    while True:
        await asyncio.sleep(1800)  # проверяем каждые 30 минут
        ts = now_ts()

        for uid, data in list(users.items()):
            stage = data.get("stage", "start")
            try:
                # Follow-up 1: зашёл, но не начал день 1 — через 2 часа
                if (stage == "start"
                        and not data.get("fu_start")
                        and ts - data.get("start_at", ts) > 2 * 3600):
                    await bot.send_message(
                        int(uid),
                        "👋 <b>Кстати, первые 2 дня — полностью бесплатно</b>\n\n"
                        "Просто попробуй. Без регистраций и оплаты.\n"
                        "40 минут — и ты поймёшь, как это работает.\n\n"
                        "👇 Начать прямо сейчас:",
                        reply_markup=day1_kb()
                    )
                    users[uid]["fu_start"] = True
                    save_users()

                # Follow-up 2: прошёл день 1, но не пошёл в день 2 — через 4 часа
                elif (stage == "day1"
                        and not data.get("fu_day1")
                        and ts - data.get("day1_at", ts) > 4 * 3600):
                    await bot.send_message(
                        int(uid),
                        "🔥 <b>Как прошёл 1-й день?</b>\n\n"
                        "2-й день ещё круче — там ты узнаешь,\n"
                        "где именно деньги в AI-фрилансе.\n\n"
                        "Студенты, которые дошли до конца,\n"
                        "берут первые заказы <b>уже через 3–5 дней.</b>\n\n"
                        "👇 Продолжай:",
                        reply_markup=day2_kb()
                    )
                    users[uid]["fu_day1"] = True
                    save_users()

                # Follow-up 3: смотрел тарифы, но не купил — через 20 часов
                elif (stage == "tariffs"
                        and not data.get("fu_tariffs")
                        and ts - data.get("tariffs_at", ts) > 20 * 3600):
                    s = get_spots()
                    await bot.send_message(
                        int(uid),
                        f"⚠️ <b>Места заканчиваются — осталось {s}</b>\n\n"
                        "Напомню: после 1-го дня полного курса —\n"
                        "<b>гарантия возврата без вопросов.</b>\n\n"
                        "Риска нет. Зато есть шанс начать зарабатывать\n"
                        "на нейросетях прямо сейчас.\n\n"
                        "👇 Выбрать тариф:",
                        reply_markup=tariffs_kb(s)
                    )
                    users[uid]["fu_tariffs"] = True
                    save_users()

            except Exception:
                pass


# ─── ЗАПУСК ────────────────────────────────────────────────────────────────────

async def main():
    print("Бот запущен!")
    asyncio.create_task(follow_up_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
