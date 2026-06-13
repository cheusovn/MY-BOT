#!/usr/bin/env python3
"""End-to-end проверки воронки бота на уровне хендлеров и бизнес-логики.

Запуск:  python3 tests/test_e2e.py
Сеть/Telegram не нужны: токен фейковый, объект `bot` подменён заглушкой,
сетевые вызовы ЮKassa мокаются. Проверяется реальная логика handlers.
"""
import os
import sys
import asyncio

# Фейковый токен валидного формата (Bot() проверяет только формат, не сеть)
os.environ.setdefault("BOT_TOKEN", "123456789:TESTTESTTESTTESTTESTTESTTESTTESTTES")
os.environ.setdefault("OPENROUTER_API_KEY", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot as m  # noqa: E402

ADMIN = str(m.ADMIN_ID)
NOW = m.now_ts

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(("✅" if cond else "❌") + f" {name}")


# ─── Заглушки Telegram ──────────────────────────────────────────────────────
class DummyBot:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def f(*a, **k):
            self.calls.append((name, a, k))
            return None
        return f


class U:
    def __init__(self, uid, first="Тест", username="user"):
        self.id = int(uid)
        self.first_name = first
        self.username = username


class Chat:
    def __init__(self, uid):
        self.id = int(uid)


class Msg:
    def __init__(self, uid, text="", photo=None, sp=None):
        self.from_user = U(uid)
        self.chat = Chat(uid)
        self.text = text
        self.caption = None
        self.photo = photo
        self.successful_payment = sp
        self.sent = []

    async def answer(self, *a, **k):
        self.sent.append(("text", a, k))

    async def answer_photo(self, *a, **k):
        self.sent.append(("photo", a, k))

    async def delete(self):
        pass


class Call:
    def __init__(self, data, uid):
        self.data = data
        self.from_user = U(uid)
        self.message = Msg(uid)

    async def answer(self, *a, **k):
        pass


class State:
    def __init__(self):
        self._d = {}
        self.state = None

    async def clear(self):
        self.state = None
        self._d = {}

    async def set_state(self, s):
        self.state = s

    async def update_data(self, **k):
        self._d.update(k)

    async def get_data(self):
        return dict(self._d)


class SP:
    def __init__(self, payload, amount_cents=497000, currency="RUB"):
        self.invoice_payload = payload
        self.total_amount = amount_cents
        self.currency = currency
        self.telegram_payment_charge_id = "charge_test"


def reset_state():
    m.users.clear()
    m.promos.clear()
    m._granted_payments.clear()
    m.events_log.setdefault("counters", {}).clear()


async def start_user(uid, first="Тест"):
    msg = Msg(uid, text="/start")
    msg.from_user = U(uid, first=first)
    await m.cmd_start(msg, State())
    return msg


# ─── Тесты ──────────────────────────────────────────────────────────────────
async def t_onboarding():
    reset_state()
    uid = "1001"
    await start_user(uid)
    check("start: пользователь создан", uid in m.users)
    check("start: стадия = start", m.users[uid].get("stage") == "start")

    await m.cb_goal(Call("goal_freelance", uid))
    check("goal: цель сохранена", m.users[uid].get("goal") == "freelance")


async def t_day_gate_normal():
    reset_state()
    uid = "1002"
    await start_user(uid)
    await m.cb_day1(Call("day1", uid))
    check("day1: записан day1_at", m.users[uid].get("day1_at"))
    check("day1: урок 1 открыт", "1" in m._days(uid))

    # сразу день 2 — должен быть закрыт (12 ч)
    await m.cb_day2(Call("day2", uid))
    check("day2 рано: НЕ открыт (стадия не day2)", m.users[uid].get("stage") != "day2")
    check("day2 рано: урок 2 не открыт", "2" not in m._days(uid))

    # прошло 13 ч — день 2 открывается
    m.users[uid]["day1_at"] = NOW() - 13 * 3600
    await m.cb_day2(Call("day2", uid))
    check("day2 через 13ч: открыт", m.users[uid].get("stage") == "day2")
    check("day2 через 13ч: урок 2 открыт", "2" in m._days(uid))


async def t_admin_bypass():
    reset_state()
    await start_user(ADMIN)
    await m.cb_day1(Call("day1", ADMIN))
    # день 2 сразу, без ожидания 12 ч
    await m.cb_day2(Call("day2", ADMIN))
    check("admin: день 2 без задержки", m.users[ADMIN].get("stage") == "day2")
    check("admin: rate_ok всегда True", m.rate_ok(ADMIN, "x", 99999) and m.rate_ok(ADMIN, "x", 99999))
    check("admin: course_gate любой день = ok", m.course_gate(ADMIN, 7)[0] == "ok")

    norm = "1003"
    await start_user(norm)
    first = m.rate_ok(norm, "k", 99999)
    second = m.rate_ok(norm, "k", 99999)
    check("user: rate_ok второй раз False", first and not second)


async def t_course_paid_flow():
    reset_state()
    uid = "1004"
    await start_user(uid)

    # до оплаты дни 3-8 закрыты
    check("course: non-buyer day3 = pay", m.course_gate(uid, 3)[0] == "pay")
    await m.cb_course_day(Call("day_3", uid))
    check("course: non-buyer не открыл день 3", "3" not in m._days(uid))

    # покупка VIP
    await m.on_paid(Msg(uid, sp=SP("course_vip")))
    check("pay: план сохранён = vip", m.users[uid].get("plan") == "vip")
    check("pay: бейдж buyer выдан", "buyer" in m._ensure_game(uid).get("badges", []))
    check("pay: is_buyer = True", m.is_buyer(uid))

    # день 3 открывается сразу
    check("course: buyer day3 = ok", m.course_gate(uid, 3)[0] == "ok")
    await m.cb_course_day(Call("day_3", uid))
    check("course: день 3 открыт", "3" in m._days(uid))

    # день 4 требует домашку дня 3
    check("course: day4 без домашки = hw", m.course_gate(uid, 4)[0] == "hw")
    await m.cb_homework(Call("hw_3", uid))
    check("course: домашка дня 3 засчитана", m.hw_done(uid, 3))

    # домашка есть, но 4 ч ещё не прошли
    check("course: day4 до 4ч = wait", m.course_gate(uid, 4)[0] == "wait")
    # прошло 5 ч с открытия дня 3
    m._days(uid)["3"]["open"] = NOW() - 5 * 3600
    check("course: day4 после 4ч = ok", m.course_gate(uid, 4)[0] == "ok")


async def t_day8_paywall():
    reset_state()
    # VIP: день 8 за доплату
    vip = "1005"
    await start_user(vip)
    await m.on_paid(Msg(vip, sp=SP("course_vip")))
    check("day8: VIP без докупки = day8pay", m.course_gate(vip, 8)[0] == "day8pay")
    check("day8: VIP has_day8 False", not m.has_day8(vip))
    # докупка 8-го дня
    await m.on_paid(Msg(vip, sp=SP("course_day8", amount_cents=179000)))
    check("day8: после докупки has_day8 True", m.has_day8(vip))
    check("day8: после докупки не day8pay", m.course_gate(vip, 8)[0] != "day8pay")

    # PRO: день 8 включён
    pro = "1006"
    await start_user(pro)
    await m.on_paid(Msg(pro, sp=SP("course_pro")))
    check("day8: PRO includes day8", m.has_day8(pro))


async def t_payment_security():
    reset_state()
    owner = "2001"
    attacker = "2002"
    await start_user(owner)
    await start_user(attacker)

    payments = {
        "P1": {"status": "succeeded", "amount": {"value": "4970.00"},
               "metadata": {"user_id": owner, "plan": "vip"}},
        "P2": {"status": "succeeded", "amount": {"value": "4970.00"},
               "metadata": {"user_id": owner, "plan": "vip"}},
    }

    async def fake_get(pid):
        return payments.get(pid)

    m.yk_get_payment = fake_get

    # владелец подтверждает свой платёж → доступ выдан
    await m.cb_ykcheck(Call("ykchk_P1:vip", owner))
    check("security: владелец получил доступ", "buyer" in m._ensure_game(owner).get("badges", []))

    # атакующий подставляет чужой payment_id → доступ НЕ выдан
    await m.cb_ykcheck(Call("ykchk_P2:vip", attacker))
    check("security: чужой платёж НЕ выдал доступ", "buyer" not in m._ensure_game(attacker).get("badges", []))


async def t_pre_checkout():
    reset_state()
    m.bot.calls.clear()

    class PCQ:
        def __init__(self, payload):
            self.id = "pcq"
            self.invoice_payload = payload

    await m.pre_checkout(PCQ("course_vip"))
    await m.pre_checkout(PCQ("course_hacker"))
    oks = [k.get("ok") for (name, a, k) in m.bot.calls if name == "answer_pre_checkout_query"]
    check("pre_checkout: валидный payload ok=True", True in oks)
    check("pre_checkout: левый payload ok=False", False in oks)


async def t_pricing():
    reset_state()
    uid = "3001"
    await start_user(uid)
    check("price: base не ниже floor", m.final_price(uid, "base") >= m.TARIFFS["base"]["floor"])
    check("price: day8 фикс 1790", m.final_price(uid, "day8") == 1790)
    check("price: day8 в TARIFFS", "day8" in m.TARIFFS)
    check("links: 8 дней курса", all(d in m.COURSE_LINKS for d in range(1, 9)))


async def main():
    m.bot = DummyBot()  # подменяем сетевой бот заглушкой
    print("─── E2E прогон воронки бота ───")
    for fn in [t_onboarding, t_day_gate_normal, t_admin_bypass, t_course_paid_flow,
               t_day8_paywall, t_payment_security, t_pre_checkout, t_pricing]:
        try:
            await fn()
        except Exception as e:
            check(f"{fn.__name__}: исключение {type(e).__name__}: {e}", False)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n── Итог: {passed}/{total} прошло ──")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
