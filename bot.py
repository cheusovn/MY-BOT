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

import os
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 817730727
BOT_USERNAME = "Trueman_ai_bot"
TRIAL_DAY_1 = "https://t.me/+5ep9DPf7eNMzZjdi"
TRIAL_DAY_2 = "https://t.me/+SpoNR-ahkJFiZTJi"
GIFT_LINK = "https://t.me/syntxaibot?start=aff_817730727"
MANAGER = "@nikolay_cheusov"
WELCOME_IMG = "welcome.jpg"

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

def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Забрать 2 дня БЕСПЛАТНО", callback_data="day1")],
        [InlineKeyboardButton(text="💰 Тарифы и цены", callback_data="tariffs")],
        [InlineKeyboardButton(text="👥 Заработать с другом", callback_data="referral")],
    ])

def day1_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 100+ нейросетей в ПОДАРОК", url=GIFT_LINK)],
        [InlineKeyboardButton(text="🚀 Открыть 1-й день", url=TRIAL_DAY_1)],
        [InlineKeyboardButton(text="✅ Я прошёл 1-й день", callback_data="day2")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])
def day2_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Открыть 2-й день", url=TRIAL_DAY_2)],
        [InlineKeyboardButton(text="✅ Я прошёл 2-й день", callback_data="tariffs")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")],
    ])

def tariffs_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Базовый — 5 900 ₽", callback_data="buy_base")],
        [InlineKeyboardButton(text="⭐ VIP с куратором — 9 900 ₽", callback_data="buy_vip")],
        [InlineKeyboardButton(text="🚀 PRO + продвижение — 15 900 ₽", callback_data="buy_pro")],
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

async def show(call, text, kb):
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await call.answer()

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    name = message.from_user.first_name or "друг"

    if user_id not in users:
        users[user_id] = {"name": name}
        save_users(users)
        try:
            await bot.send_message(ADMIN_ID, f"🔔 Новый пользователь: {name} (ID: {user_id})")
        except: pass

    text = (
        f"👋 Привет, <b>{name}</b>!\n\n"
        "🤖 Добро пожаловать в <b>True AI Academy</b> — "
        "обучение нейросетям с нуля до профи за 7 дней.\n\n"
        "🎁 <b>Первые 2 дня — БЕСПЛАТНО!</b>\n"
        "💰 Ты научишься зарабатывать на AI, даже если никогда "
        "этим не занимался.\n\n"
        "👇 Жми кнопку и начинай прямо сейчас:"
    )
    if os.path.exists(WELCOME_IMG):
        await message.answer_photo(photo=FSInputFile(WELCOME_IMG), caption=text, reply_markup=start_kb())
    else:
        await message.answer(text, reply_markup=start_kb())

@dp.callback_query(lambda c: c.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    name = call.from_user.first_name or "друг"
    text = f"🏠 <b>Главное меню</b>\n\nПривет, {name}! Выбери, что тебе нужно 👇"
    await show(call, text, start_kb())

@dp.callback_query(lambda c: c.data == "day1")
async def cb_day1(call: CallbackQuery):
    text = (
        "🎉 <b>ПОЗДРАВЛЯЮ! Ты сделал первый шаг в мир AI!</b>\n\n"
        "━━━━━━━━━━━━━━━\n"
        "📅 <b>ДЕНЬ 1 — ТВОЙ СТАРТ В НЕЙРОСЕТЯХ</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "🎁 <b>СРАЗУ ЗАБИРАЕШЬ ПОДАРОК:</b>\n"
        "💎 <b>100+ топовых нейросетей</b> — моя личная подборка,\n"
        "за которую другие платят тысячи рублей. Твоя — бесплатно!\n\n"
        "🚀 <b>Что ты сделаешь уже сегодня:</b>\n"
        "✨ Запустишь свою <b>первую нейросеть</b>\n"
        "🖼 Создашь первые <b>картинки по готовому промпту</b>\n"
        "😍 Увидишь, как из пары слов рождается шедевр\n\n"
        "💡 <i>Уже на 1-м дне ты поймёшь — это проще, чем кажется!</i>\n\n"
        "👇 Жми кнопку, погружайся, а потом возвращайся за <b>2-м днём</b> 🔥"
    )
    await show(call, text, day1_kb())

@dp.callback_query(lambda c: c.data == "day2")
async def cb_day2(call: CallbackQuery):
    text = (
        "🔥 <b>ОГОНЬ! Ты прошёл 1-й день — ты уже в игре!</b>\n\n"
        "━━━━━━━━━━━━━━━\n"
        "📅 <b>ДЕНЬ 2 — ПРОКАЧКА ДО НОВОГО УРОВНЯ</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "⚡ Сегодня ты перестаёшь быть новичком!\n\n"
        "🎨 <b>Что тебя ждёт:</b>\n"
        "🔸 Углубляемся в нейросети по-серьёзному\n"
        "🔸 Делаешь <b>профессиональные генерации</b>\n"
        "🔸 Учишься <b>писать промпты САМ</b> — без шаблонов\n"
        "🔸 Создаёшь работы, за которые <b>уже платят деньги</b> 💸\n\n"
        "💪 <i>После 2-го дня ты сможешь брать первые заказы!</i>\n\n"
        "👉 Открывай 2-й день — а в конце тебя ждёт <b>особый сюрприз</b> 🎁"
    )
    await show(call, text, day2_kb())

@dp.callback_query(lambda c: c.data == "tariffs")
async def cb_tariffs(call: CallbackQuery):
    text = (
        "🔥 <b>Ты прошёл бесплатную часть! Теперь — полный курс:</b>\n\n"
        "💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n\n"
        "━━━━━━━━━━━━━━━\n"
        "📦 <b>БАЗОВЫЙ — 5 900 ₽</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "✅ Все 7 дней курса\n"
        "✅ Доступ навсегда\n\n"
        "━━━━━━━━━━━━━━━\n"
        "⭐ <b>VIP С КУРАТОРОМ — 9 900 ₽</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "✅ Всё из «Базового»\n"
        "✅ Личный куратор + проверка ДЗ\n"
        "✅ Закрытый чат поддержки\n\n"
        "━━━━━━━━━━━━━━━\n"
        "🚀 <b>VIP + ПРОДВИЖЕНИЕ — 15 900 ₽</b>\n"
        "🏆 <i>Выбор тех, кто хочет ЗАРАБАТЫВАТЬ</i>\n"
        "━━━━━━━━━━━━━━━\n"
        "✅ Всё из «VIP с куратором»\n"
        "💼 <b>Где брать заказы</b> — проверенные площадки\n"
        "🤝 <b>Где брать клиентов</b> — пошаговая система\n"
        "🔥 <b>Поиск вирусного контента</b> — что залетает\n"
        "📢 <b>Реклама</b> — как настроить и не слить бюджет\n"
        "📱 <b>SMM-маркетинг</b> — раскрутка с нуля\n"
        "🧲 <b>Лид-магниты и воронки</b> — клиенты на автопилоте\n"
        "🎯 <b>Как набрать 1 млн просмотров</b>\n\n"
        "💸 <i>С этим тарифом ты не просто учишься — ты выходишь на доход!</i>\n\n"
        "⏰ <b>Все цены с учётом акции!</b>\n"
        "Завтра будет повышение цен. Выбирай 👇"
    )
    await show(call, text, tariffs_kb())

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery):
    plan = {
        "buy_base": "📦 Базовый — 5 900 ₽",
        "buy_vip": "⭐ VIP с куратором — 9 900 ₽",
        "buy_pro": "🚀 PRO + продвижение — 15 900 ₽",
    }.get(call.data, "Тариф")
    text = (
        f"✅ Отличный выбор!\n\nТы выбрал тариф:\n<b>{plan}</b>\n\n"
        "Чтобы оформить доступ — напиши менеджеру 👇\n"
        "Он пришлёт реквизиты и откроет полный курс 🚀\n\n"
        "💡 <b>Есть промокод друга?</b> Назови его менеджеру и получи <b>скидку 500 ₽</b>!"
    )
    await show(call, text, to_manager_kb())
    name = call.from_user.first_name or "Юзер"
    uname = f"@{call.from_user.username}" if call.from_user.username else "нет username"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 <b>НОВАЯ ЗАЯВКА!</b>\n\n👤 {name} ({uname})\n🆔 ID: {call.from_user.id}\n📦 Тариф: {plan}"
        )
    except: pass

@dp.callback_query(lambda c: c.data == "referral")
async def cb_referral(call: CallbackQuery, state: FSMContext):
    user_id = str(call.from_user.id)
    existing = None
    for code, uid in promos.items():
        if uid == user_id:
            existing = code
            break

    if existing:
        text = (
            "👥 <b>ЗАРАБОТОК НА ДРУЗЬЯХ</b>\n\n"
            "🎁 <b>Ты получаешь 30% с каждой оплаты друга на карту</b>\n"
            "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
            f"🎫 <b>Твой промокод:</b> <code>{existing}</code>\n\n"
            "📲 <b>Как это работает:</b>\n"
            "1️⃣ Дай другу свой промокод\n"
            "2️⃣ Друг называет его менеджеру при оплате\n"
            "3️⃣ Ты получаешь 30% на карту 💸"
        )
        await show(call, text, back_kb())
    else:
        await state.set_state(PromoState.waiting)
        text = (
            "👥 <b>ЗАРАБОТОК НА ДРУЗЬЯХ</b>\n\n"
            "🎁 <b>Ты получаешь 30% с каждой оплаты друга на карту</b>\n"
            "🎁 Друг получает <b>скидку 500 ₽</b>\n\n"
            "✍️ <b>Придумай свой промокод и напиши его сообщением</b>\n"
            "(например: <code>MAX2024</code> или <code>NEYRO</code>)\n\n"
            "Этот промокод друзья будут называть менеджеру при оплате 👇"
        )
        try:
            await call.message.delete()
        except: pass
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
        "✅ <b>Отлично! Твой промокод создан!</b>\n\n"
        f"🎫 <b>Промокод:</b> <code>{code}</code>\n\n"
        "📲 <b>Как зарабатывать:</b>\n"
        "1️⃣ Дай другу свой промокод\n"
        "2️⃣ Друг называет его менеджеру при оплате\n"
        "3️⃣ Ты получаешь <b>30% на карту</b> 💸\n\n"
        "Делись промокодом и зарабатывай! 🚀"
    )
    await message.answer(text, reply_markup=back_kb())

    name = message.from_user.first_name or "Юзер"
    uname = f"@{message.from_user.username}" if message.from_user.username else "нет username"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🎫 <b>Новый промокод создан</b>\n\n👤 {name} ({uname})\n🆔 ID: {user_id}\n🎫 Промокод: <code>{code}</code>"
        )
    except: pass

@dp.message(Command("trial"))
async def cmd_trial(message: Message):
    text = "🎁 <b>Держи доступ к 1-му дню БЕСПЛАТНО:</b>\n\nИзучи материалы и возвращайся за 2-м днём 🚀"
    await message.answer(text, reply_markup=day1_kb())

@dp.message(Command("tariffs"))
async def cmd_tariffs(message: Message):
    text = (
        "💰 <b>ТАРИФЫ ОБУЧЕНИЯ</b>\n\n"
        "📦 <b>Базовый — 5 900 ₽</b>\n⭐ <b>VIP с куратором — 9 900 ₽</b>\n"
        "🚀 <b>PRO + продвижение — 15 900 ₽</b>\n\nВыбери свой тариф 👇"
    )
    await message.answer(text, reply_markup=tariffs_kb())

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ <b>ПОМОЩЬ И ПОДДЕРЖКА</b>\n\n<b>Команды:</b>\n"
        "/start — главное меню\n/trial — бесплатный доступ\n"
        "/tariffs — тарифы\n\n"
        "💬 Остались вопросы? Напиши менеджеру 👇"
    )
    await message.answer(text, reply_markup=to_manager_kb())

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
            f"🎫 Промокод <b>{code}</b>\n👤 Владелец: {owner_name}\n🆔 ID: <code>{owner}</code>"
        )
    else:
        await message.answer(f"❌ Промокод <b>{code}</b> не найден.")

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())