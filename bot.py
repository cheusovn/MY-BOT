import asyncio
import json
import os
import logging
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
SPOTS_LEFT = 23

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

DATA_DIR = "/data" if os.path.exists("/data") else "."
PROMO_FILE = os.path.join(DATA_DIR, "promo.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


promos = load_json(PROMO_FILE)
users = load_json(USERS_FILE)


def save_promos(data): save_json(PROMO_FILE, data)
def save_users(data): save_json(USERS_FILE, data)


class PromoState(StatesGroup):
    waiting = State()


# ─── КЛАВИАТУРЫ ───────────────────────────────────────────────────────────────

def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 100+ нейросетей — 100+ дней БЕСПЛАТНО", callback_data="free_gift")],
        [InlineKeyboardButton(text="🎓 Попробовать курс — 2 дня бесплатно", callback_data="day1")],
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
        [InlineKeyboardButton(text="🚀 Открыть 1-й день", url=TRIAL_DAY_1)],
        [InlineKeyboardButton(text="✅ Прошёл 1-й день →", callback_data="day2")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def day2_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Открыть 2-й день", url=TRIAL_DAY_2)],
        [InlineKeyboardButton(text="✅ Готово — открыть специальное предложение 🎁", callback_data="special_tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def tariffs_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 PRO + продвижение — 7 900 ₽", callback_data="buy_pro")],
        [InlineKeyboardButton(text="⭐ VIP с куратором — 4 900 ₽  ← ТОПЧИК", callback_data="buy_vip")],
        [InlineKeyboardButton(text="📦 Базовый — 2 900 ₽", callback_data="buy_base")],
        [
            InlineKeyboardButton(text="🛡 Гарантия", callback_data="guarantee"),
            InlineKeyboardButton(text="❓ Вопросы", callback_data="faq"),
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def to_manager_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру", url=f"https://t.me/{MANAGER.lstrip('@')}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


def back_to_tariffs_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад к тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])


# ─── ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ──────────────────────────────────────────────────

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

    if user_id not in users:
        users[user_id] = {"name": name}
        save_users(users)
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 Новый пользователь: <b>{name}</b>\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"👥 Всего пользователей: {len(users)}"
            )
        except Exception:
            pass

    text = (
        f"👋 <b>{name}, привет!</b>\n\n"
        f"Ты в <b>True AI Academy</b> — школе, где уже <b>{STUDENTS_COUNT} человек</b>\n"
        "научились зарабатывать на нейросетях.\n\n"
        "За 7 дней — путь от «что такое AI?» до первых заказов.\n"
        "Без опыта. Без технических знаний. С нуля.\n\n"
        "👇 Выбери, с чего начать:"
    )

    if os.path.exists(WELCOME_IMG):
        try:
            await message.answer_photo(
                photo=FSInputFile(WELCOME_IMG),
                caption=text,
                reply_markup=start_kb()
            )
        except Exception:
            await message.answer(text, reply_markup=start_kb())
    else:
        await message.answer(text, reply_markup=start_kb())


@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    name = call.from_user.first_name or "друг"
    text = (
        f"🏠 <b>Главное меню</b>\n\n"
        f"{name}, что интересует? 👇"
    )
    await show(call, text, start_kb())


@dp.callback_query(lambda c: c.data == "free_gift")
async def cb_free_gift(call: CallbackQuery):
    text = (
        "🔥 <b>ПОДАРОК — 100+ НЕЙРОСЕТЕЙ НА 100+ ДНЕЙ</b>\n\n"
        "Прямо сейчас получаешь доступ к лучшим\n"
        "нейросетям мира — <b>совершенно бесплатно</b>.\n\n"
        "<b>Что входит в подарок:</b>\n"
        "🎨 Midjourney — изображения уровня рекламных студий\n"
        "🎬 Kling, Runway, Veo — AI-видео за минуты\n"
        "🤖 ChatGPT Plus — тексты, идеи, сценарии\n"
        "🎵 Suno — музыка и саундтреки под ключ\n"
        "🔊 ElevenLabs — реалистичная озвучка\n"
        "📸 Nano Banana — фото и визуалы\n"
        "и ещё <b>95+ инструментов</b>\n\n"
        "──────────────────────────\n"
        "💡 Это не триал на 3 дня.\n"
        "Это <b>100+ дней</b> полноценного доступа.\n"
        "Без карты. Без оплаты. Прямо сейчас.\n"
        "──────────────────────────\n\n"
        f"⚡ Уже <b>{STUDENTS_COUNT} человек</b> забрали подарок.\n"
        "Предложение ограничено по времени:\n\n"
        "👇 Нажми и получи немедленно:"
    )
    await show(call, text, free_gift_kb())


@dp.callback_query(lambda c: c.data == "day1")
async def cb_day1(call: CallbackQuery):
    text = (
        "🎉 <b>Добро пожаловать в первый шаг!</b>\n\n"
        "┌─────────────────────────┐\n"
        "│  📅  ДЕНЬ 1 — ПОГРУЖЕНИЕ  │\n"
        "└─────────────────────────┘\n\n"
        "<b>Что ты сделаешь в 1-й день:</b>\n"
        "▸ Запустишь первую нейросеть за 5 минут\n"
        "▸ Создашь изображения, которые удивят окружающих\n"
        "▸ Напишешь первый рабочий промпт\n"
        "▸ Поймёшь, <i>где деньги в AI</i>\n\n"
        "💬 <i>«После 1-го дня понял: это не сложно.\n"
        "Просто боялся начать» — Алексей, студент</i>\n\n"
        "👇 Открывай 1-й день прямо сейчас:"
    )
    await show(call, text, day1_kb())


@dp.callback_query(lambda c: c.data == "day2")
async def cb_day2(call: CallbackQuery):
    text = (
        "🔥 <b>День 1 пройден! Ты уже не новичок.</b>\n\n"
        "┌─────────────────────────┐\n"
        "│  📅  ДЕНЬ 2 — ПРОКАЧКА    │\n"
        "└─────────────────────────┘\n\n"
        "Сегодня перейдёшь черту между\n"
        "«просто интересно» и «могу на этом зарабатывать».\n\n"
        "<b>Программа 2-го дня:</b>\n"
        "▸ Профессиональные генерации — уровень эксперта\n"
        "▸ Пишешь промпты сам, без шаблонов\n"
        "▸ Создаёшь работы, за которые <b>уже платят 5–30k ₽</b>\n"
        "▸ Видишь воронку: навык → заказ → деньги\n\n"
        "💬 <i>«После 2-го дня взял первый заказ на 8 000 ₽»\n"
        "— Марина, 3 недели обучения</i>\n\n"
        "⚡ После 2-го дня откроется <b>специальное предложение</b>\n"
        "только для тех, кто дошёл до конца. 👇"
    )
    await show(call, text, day2_kb())


@dp.callback_query(lambda c: c.data == "special_tariffs")
async def cb_special_tariffs(call: CallbackQuery):
    text = (
        "🔐 <b>ЗАКРЫТОЕ ПРЕДЛОЖЕНИЕ</b>\n"
        "Только для тех, кто прошёл оба дня\n\n"
        f"⚠️ Осталось мест по этой цене: <b>{SPOTS_LEFT}</b>\n\n"
        "──────────────────────────\n"
        "Ты только что <b>своими руками</b> убедился — это работает.\n"
        "Теперь реши, до куда идёшь дальше.\n\n"
        "🚀 <b>PRO + ПРОДВИЖЕНИЕ — 7 900 ₽</b>\n"
        "Для тех, кто хочет зарабатывать системно:\n"
        "где брать заказы, как продвигаться, вирусный контент,\n"
        "SMM, реклама без слива бюджета, 1 млн просмотров\n\n"
        "⭐ <b>VIP С КУРАТОРОМ — 4 900 ₽</b>  ← выбирает большинство\n"
        "Все 7 дней + личный куратор + проверка ДЗ + чат 24/7\n"
        "Доступ навсегда. Обратная связь на каждом шаге.\n\n"
        "📦 <b>БАЗОВЫЙ — 2 900 ₽</b>\n"
        "Все 7 дней курса, доступ навсегда, в своём темпе\n\n"
        "──────────────────────────\n"
        "🛡 Гарантия: не понравится 1-й день курса — вернём деньги.\n"
        "Без вопросов и условий.\n\n"
        "👇 Выбирай — менеджер ответит за 5 минут:"
    )
    await show(call, text, tariffs_kb())


@dp.callback_query(lambda c: c.data == "tariffs")
async def cb_tariffs(call: CallbackQuery):
    text = (
        "💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n\n"
        f"⚠️ Осталось мест по акционной цене: <b>{SPOTS_LEFT}</b>\n\n"
        "──────────────────────────\n"
        "🚀 <b>PRO + ПРОДВИЖЕНИЕ — 7 900 ₽</b>\n"
        "──────────────────────────\n"
        "Для тех, кто хочет не просто учиться, а <b>выйти на доход</b>:\n"
        "✅ Всё из VIP\n"
        "💼 Где брать заказы — проверенные площадки\n"
        "🤝 Система поиска клиентов под ключ\n"
        "🔥 Поиск вирусного контента (что залетает)\n"
        "📢 Реклама: настроить и не слить бюджет\n"
        "📱 SMM-маркетинг с нуля\n"
        "🧲 Лид-магниты и воронки продаж\n"
        "🎯 Как набрать 1 млн просмотров\n\n"
        "──────────────────────────\n"
        "⭐ <b>VIP С КУРАТОРОМ — 4 900 ₽</b>  ← выбирает большинство\n"
        "──────────────────────────\n"
        "✅ Все 7 дней курса\n"
        "✅ Личный куратор + проверка домашних заданий\n"
        "✅ Закрытый чат поддержки 24/7\n"
        "✅ Доступ навсегда\n\n"
        "──────────────────────────\n"
        "📦 <b>БАЗОВЫЙ — 2 900 ₽</b>\n"
        "──────────────────────────\n"
        "✅ Все 7 дней курса\n"
        "✅ Доступ навсегда\n\n"
        "🛡 <b>Гарантия:</b> если после 1-го дня курс не понравится —\n"
        "вернём деньги. Без вопросов.\n\n"
        "👇 Выбирай тариф:"
    )
    await show(call, text, tariffs_kb())


@dp.callback_query(lambda c: c.data == "results")
async def cb_results(call: CallbackQuery):
    text = (
        "🏆 <b>РЕЗУЛЬТАТЫ СТУДЕНТОВ</b>\n\n"
        f"За полгода через академию прошли <b>{STUDENTS_COUNT}+ человек.</b>\n"
        "Вот что говорят те, кто уже учится:\n\n"
        "──────────────────────────\n"
        "💬 <b>Марина, фрилансер:</b>\n"
        "<i>«Взяла первый заказ через 3 дня после курса.\n"
        "8 000 ₽ за генерацию логотипов. В шоке, что так просто»</i>\n\n"
        "──────────────────────────\n"
        "💬 <b>Алексей, менеджер:</b>\n"
        "<i>«Сначала боялся — я же не технарь. Оказалось,\n"
        "нейросети проще, чем Excel. Теперь делаю\n"
        "контент для клиентов, +30k/мес»</i>\n\n"
        "──────────────────────────\n"
        "💬 <b>Ирина, работает из дома:</b>\n"
        "<i>«Искала занятие, которое не привязывает к офису.\n"
        "После курса нашла 4 заказчика на иллюстрации.\n"
        "Зарабатываю 25–40k ₽ в месяц»</i>\n\n"
        "──────────────────────────\n"
        "💬 <b>Дмитрий, владелец бизнеса:</b>\n"
        "<i>«Теперь весь контент для бизнеса делаю сам.\n"
        "Экономлю 50 000 ₽/мес на дизайнерах»</i>\n\n"
        "🎁 <b>Начни с бесплатных 2 дней — и убедись сам</b>"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 100+ нейросетей — БЕСПЛАТНО", callback_data="free_gift")],
        [InlineKeyboardButton(text="🎓 Попробовать курс бесплатно", callback_data="day1")],
        [InlineKeyboardButton(text="💰 Смотреть тарифы", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data == "faq")
async def cb_faq(call: CallbackQuery):
    text = (
        "❓ <b>ЧАСТЫЕ ВОПРОСЫ</b>\n\n"
        "──────────────────────────\n"
        "❔ <b>Нужны ли технические знания?</b>\n"
        "Нет. Курс создан для людей без опыта в IT.\n"
        "Если умеешь пользоваться телефоном — разберёшься.\n\n"
        "──────────────────────────\n"
        "❔ <b>За какое время реально заработать?</b>\n"
        "Первые заказы студенты берут на 3–7 день курса.\n"
        "Стабильный доход 30–80k ₽/мес — через 2–4 недели практики.\n\n"
        "──────────────────────────\n"
        "❔ <b>А вдруг не получится?</b>\n"
        "Поэтому есть бесплатные 2 дня — проверь сам.\n"
        "Плюс гарантия возврата денег после 1-го дня курса.\n\n"
        "──────────────────────────\n"
        "❔ <b>Когда начинается обучение?</b>\n"
        "Сразу после оплаты. Доступ 24/7, в своём темпе.\n\n"
        "──────────────────────────\n"
        "❔ <b>Сколько времени в день нужно?</b>\n"
        "1–2 часа достаточно. Курс заточен под занятых людей.\n\n"
        "──────────────────────────\n\n"
        "Остались вопросы? Менеджер ответит за 5 минут 👇"
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
        "Мы уверены в качестве курса.\n"
        "Поэтому даём честную гарантию:\n\n"
        "▸ Пройди <b>1-й день</b> полного курса\n"
        "▸ Если он не понравился — напиши менеджеру\n"
        "▸ Вернём <b>100% оплаты</b> без вопросов и условий\n\n"
        "──────────────────────────\n\n"
        "Почему мы можем себе это позволить?\n\n"
        f"Потому что из <b>{STUDENTS_COUNT}+ студентов</b> возвратов\n"
        "было единицы. Курс реально работает.\n\n"
        "💬 <i>«Очень переживала перед покупкой.\n"
        "Гарантия помогла решиться. Возврат не понадобился»\n"
        "— Ольга, студентка</i>"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад к тарифам", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ]))


@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    plans = {
        "buy_base": ("📦 Базовый — 2 900 ₽", "базовый"),
        "buy_vip":  ("⭐ VIP с куратором — 4 900 ₽", "VIP"),
        "buy_pro":  ("🚀 PRO + продвижение — 7 900 ₽", "PRO"),
    }
    plan_label, plan_short = plans.get(call.data, ("Тариф", "выбранный"))

    text = (
        f"✅ <b>Отличный выбор — тариф {plan_short}!</b>\n\n"
        "Менеджер пришлёт реквизиты и откроет доступ\n"
        "в течение нескольких минут после оплаты. 🚀\n\n"
        "💡 <b>Есть промокод друга?</b>\n"
        "Назови его менеджеру — получишь <b>скидку 500 ₽</b>.\n\n"
        "🛡 Напомни: гарантия возврата действует\n"
        "после 1-го дня полного курса."
    )
    await show(call, text, to_manager_kb())

    name = call.from_user.first_name or "Юзер"
    uname = f"@{call.from_user.username}" if call.from_user.username else "нет username"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 <b>НОВАЯ ЗАЯВКА!</b>\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: <code>{call.from_user.id}</code>\n"
            f"📦 Тариф: {plan_label}"
        )
    except Exception:
        pass


@dp.callback_query(lambda c: c.data == "referral")
async def cb_referral(call: CallbackQuery, state: FSMContext):
    user_id = str(call.from_user.id)
    existing = next((code for code, uid in promos.items() if uid == user_id), None)

    if existing:
        text = (
            "👥 <b>ТВОЯ РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
            "🎁 <b>Ты получаешь 30%</b> с каждой оплаты друга — на карту\n"
            "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
            f"🎫 <b>Твой промокод:</b> <code>{existing}</code>\n\n"
            "<b>Как зарабатывать:</b>\n"
            "1️⃣ Поделись промокодом с другом\n"
            "2️⃣ Друг называет его менеджеру при оплате\n"
            "3️⃣ 30% зачисляется на карту 💸\n\n"
            "💡 <i>Пример: с тарифа VIP (4 900₽) приходит\n"
            "1 470 ₽ за одного приглашённого</i>"
        )
        await show(call, text, back_kb())
    else:
        await state.set_state(PromoState.waiting)
        text = (
            "👥 <b>ПАРТНЁРСКАЯ ПРОГРАММА</b>\n\n"
            "🎁 <b>Ты получаешь 30%</b> с каждой оплаты друга — на карту\n"
            "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
            "💡 <i>Пример: 3 друга купили VIP → 4 410 ₽ на карту</i>\n\n"
            "✍️ <b>Придумай свой промокод и напиши его сообщением:</b>\n"
            "(3–20 символов, только буквы и цифры)\n"
            "Пример: <code>IVAN25</code> или <code>NEYRO</code>\n\n"
            "Этот код друзья называют менеджеру при оплате 👇"
        )
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer(text, reply_markup=back_kb())
        await call.answer()


@dp.message(PromoState.waiting)
async def process_promo(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    code = message.text.strip().upper().replace(" ", "")

    if not code or len(code) < 3 or len(code) > 20:
        await message.answer("❌ Промокод должен быть от 3 до 20 символов. Попробуй ещё раз ✍️")
        return
    if not code.replace("_", "").isalnum():
        await message.answer("❌ Только буквы и цифры. Попробуй ещё раз ✍️")
        return
    if code in promos and promos[code] != user_id:
        await message.answer("❌ Такой промокод уже занят 😔\nПридумай другой ✍️")
        return

    promos[code] = user_id
    save_promos(promos)
    await state.clear()

    text = (
        "✅ <b>Промокод создан!</b>\n\n"
        f"🎫 <b>Твой промокод:</b> <code>{code}</code>\n\n"
        "<b>Как поделиться — скопируй и отправь другу:</b>\n\n"
        f"<i>Привет! Учусь в True AI Academy — нейросети, заработок, реально круто.\n"
        f"Первые 2 дня бесплатно: @{BOT_USERNAME}\n"
        f"Промокод при оплате: {code} — скидка 500₽</i>\n\n"
        "💸 После оплаты друга — 30% сразу на карту!"
    )
    await message.answer(text, reply_markup=back_kb())

    name = message.from_user.first_name or "Юзер"
    uname = f"@{message.from_user.username}" if message.from_user.username else "нет username"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🎫 <b>Новый промокод</b>\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🎫 Промокод: <code>{code}</code>"
        )
    except Exception:
        pass


# ─── КОМАНДЫ ──────────────────────────────────────────────────────────────────

@dp.message(Command("trial"))
async def cmd_trial(message: Message):
    text = (
        "🎁 <b>Бесплатный доступ — 1-й день:</b>\n\n"
        "Изучи материал и возвращайся за 2-м днём 🚀"
    )
    await message.answer(text, reply_markup=day1_kb())


@dp.message(Command("tariffs"))
async def cmd_tariffs(message: Message):
    text = (
        f"💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n\n"
        f"⚠️ Осталось мест по акционной цене: <b>{SPOTS_LEFT}</b>\n\n"
        "🚀 <b>PRO + продвижение — 7 900 ₽</b>\n"
        "⭐ <b>VIP с куратором — 4 900 ₽</b>  ← выбирает большинство\n"
        "📦 <b>Базовый — 2 900 ₽</b>\n\n"
        "👇 Выбери свой тариф:"
    )
    await message.answer(text, reply_markup=tariffs_kb())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ <b>ПОМОЩЬ И ПОДДЕРЖКА</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/trial — бесплатный доступ\n"
        "/tariffs — тарифы\n\n"
        "💬 Остались вопросы? Менеджер ответит за 5 минут 👇"
    )
    await message.answer(text, reply_markup=to_manager_kb())


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    total_users = len(users)
    total_promos = len(promos)
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"🎫 Промокодов: <b>{total_promos}</b>"
    )
    await message.answer(text)


@dp.message(Command("promo"))
async def cmd_promo_check(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Формат: <code>/promo КОД</code>\nПример: /promo MAX2024")
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


# ─── ЗАПУСК ────────────────────────────────────────────────────────────────────

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
