# -*- coding: utf-8 -*-
"""Генератор PDF лид-магнита — запускать локально, результат коммитить в репо."""
import os
from fpdf import FPDF

FONT_R = "C:/Windows/Fonts/arial.ttf"
FONT_B = "C:/Windows/Fonts/arialbd.ttf"
OUT = "lead_magnet.pdf"

AGENTS = [
    {
        "num": "01", "name": "АНАЛИТИК",
        "what": "Каждый понедельник в 9:00 собирает недельный отчёт: охваты, показы, лучшие и худшие посты.",
        "tool": "Instagram Graph API + OpenRouter (GPT-4o-mini)",
        "prompt": "Проанализируй метрики Instagram за неделю: [данные]\nВыдели: топ-3 поста по охвату, худший пост и почему,\nрекомендации на следующую неделю.\nФормат: таблица + 3 вывода.",
        "result": "0 минут на аналитику. Точно знаю что работает.",
    },
    {
        "num": "02", "name": "ОХОТНИК ЗА ТРЕНДАМИ",
        "what": "Ищет вирусные темы в нише AI каждое утро -- что набирает просмотры у конкурентов.",
        "tool": "DuckDuckGo Search + Claude Sonnet",
        "prompt": "Найди 5 трендовых тем в нише AI для бизнеса за последние 3 дня.\nДля каждой: заголовок, почему вирусная, идея поста.\nФокус: предприниматели, которые хотят экономить время.",
        "result": "Контент-план готов за 5 минут вместо 2 часов.",
    },
    {
        "num": "03", "name": "ШПИОН ЗА КОНКУРЕНТАМИ",
        "what": "Мониторит топ-5 конкурентов и находит их залетевшие посты для адаптации.",
        "tool": "Meta Graph API + OpenRouter",
        "prompt": "Проанализируй этот пост конкурента с высоким ER: [текст]\nЧто сделало его виральным? Хук, структура, CTA.\nПредложи 3 варианта похожего поста для моей ниши.",
        "result": "Беру лучшее у конкурентов и адаптирую под себя.",
    },
    {
        "num": "04", "name": "КОПИРАЙТЕР",
        "what": "Пишет хуки, описания и хештеги под каждый пост за 30 секунд.",
        "tool": "Claude Sonnet через OpenRouter",
        "prompt": "Напиши 5 хуков для Instagram-поста.\nТема: [тема]. Ниша: нейросети и AI для бизнеса.\nАудитория: предприниматели 25-40 лет. Стиль: дерзкий.\nПример: Твой SMM-щик стоит 60 000 руб. Мой -- 0 руб.",
        "result": "120+ хуков за месяц. Лучшие дали x3 к охватам.",
    },
    {
        "num": "05", "name": "ПЛАНИРОВЩИК",
        "what": "Составляет контент-план на 30 дней с темами, форматами и временем публикации.",
        "tool": "Claude Sonnet + данные аналитики",
        "prompt": "Составь контент-план на 30 дней для Instagram.\nНиша: AI-инструменты для бизнеса. Цель: рост + прогрев к курсу.\nФорматы: карусели 60%, Reels 30%, Stories 10%.",
        "result": "Месяц контента за 20 минут. Без творческого кризиса.",
    },
    {
        "num": "06", "name": "ДИЗАЙНЕР КАРУСЕЛЕЙ",
        "what": "Создаёт слайды карусели по референсу. 10 слайдов за 10 минут и 70 руб.",
        "tool": "Nano Banana 2 (Gemini 3.1) через OpenRouter",
        "prompt": "Instagram carousel slide 1080x1350.\nBlack bg #0a0a0a, lime accent #c8ff00, bold font.\nTitle: [ЗАГОЛОВОК НА РУССКОМ]\nElements: 3D mockup, glass cards, glow effect.",
        "result": "Дизайнер берёт 5-15K руб. Агент -- 7 руб. за слайд.",
    },
    {
        "num": "07", "name": "ВОРОНКА ПРОДАЖ",
        "what": "Автоматически отвечает на кодовое слово в комментах и ведёт к покупке курса.",
        "tool": "Meta Webhook + Telegram Bot (aiogram)",
        "prompt": "Схема воронки:\nКарусель -> CTA пиши АГЕНТЫ -> автоответ в комменте\n-> DM со ссылкой -> Telegram-бот -> подписка канала\n-> лид-магнит -> 2 дня бесплатно -> продажа",
        "result": "Конверсия 3-5% от комментария до покупки. Работает 24/7.",
    },
    {
        "num": "08", "name": "ПУБЛИКАТОР",
        "what": "Публикует контент одновременно в Instagram, Threads и Facebook по расписанию.",
        "tool": "Meta Graph API + cron-расписание",
        "prompt": "Расписание публикаций:\nВт, Чт, Пт -- карусели в 10:00 и 18:00\nЕжедневно -- Stories в 12:00\nПн, Ср, Вс -- Reels в 19:00",
        "result": "Три площадки покрыты. Не думаю когда публиковать.",
    },
]


def build():
    pdf = FPDF()
    pdf.add_font("A", "", FONT_R)
    pdf.add_font("A", "B", FONT_B)
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── ОБЛОЖКА ──────────────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(10, 10, 10); pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(200, 255, 0)
    pdf.rect(0, 0, 210, 7, "F")
    pdf.rect(0, 290, 210, 7, "F")

    pdf.set_font("A", "B", 32); pdf.set_text_color(200, 255, 0)
    pdf.set_y(35)
    pdf.set_x(10); pdf.multi_cell(190, 14, "8 НЕЙРОСЕТЕЙ\nКОТОРЫЕ ВЕДУТ\nМОЙ INSTAGRAM", align="C")

    pdf.set_font("A", "", 15); pdf.set_text_color(255, 255, 255)
    pdf.set_y(128)
    pdf.set_x(10); pdf.multi_cell(190, 9, "На автопилоте. Без команды. Без бюджета.", align="C")

    pdf.set_font("A", "B", 13); pdf.set_text_color(200, 255, 0)
    pdf.set_y(160)
    pdf.set_x(10); pdf.multi_cell(190, 8, "Инструменты + Промпты + Схемы", align="C")

    pdf.set_font("A", "", 10); pdf.set_text_color(120, 120, 120)
    pdf.set_y(240)
    pdf.set_x(10); pdf.multi_cell(190, 7, "by @nikolay_cheusov  |  TRUE AI ACADEMY", align="C")

    # ── СЛАЙДЫ АГЕНТОВ ───────────────────────────────────────────────────────────
    for ag in AGENTS:
        pdf.add_page()
        pdf.set_fill_color(248, 248, 248); pdf.rect(0, 0, 210, 297, "F")
        pdf.set_fill_color(200, 255, 0); pdf.rect(0, 0, 5, 297, "F")

        pdf.set_font("A", "B", 56); pdf.set_text_color(230, 230, 230)
        pdf.set_xy(10, 6); pdf.cell(30, 20, ag["num"])

        pdf.set_font("A", "B", 19); pdf.set_text_color(15, 15, 15)
        pdf.set_xy(12, 26)
        pdf.multi_cell(186, 9, f"АГЕНТ {ag['num']}: {ag['name']}")

        pdf.set_fill_color(200, 255, 0)
        pdf.rect(12, pdf.get_y() + 1, 186, 2, "F")

        y = pdf.get_y() + 7
        pdf.set_font("A", "B", 9); pdf.set_text_color(130, 130, 130)
        pdf.set_xy(12, y); pdf.cell(0, 6, "ЧТО ДЕЛАЕТ:", ln=True)
        pdf.set_font("A", "", 11); pdf.set_text_color(15, 15, 15)
        pdf.set_x(12); pdf.multi_cell(186, 6, ag["what"])

        pdf.set_y(pdf.get_y() + 3)
        pdf.set_font("A", "B", 9); pdf.set_text_color(130, 130, 130)
        pdf.set_x(12); pdf.cell(0, 6, "ИНСТРУМЕНТ:", ln=True)
        pdf.set_font("A", "", 11); pdf.set_text_color(15, 15, 15)
        pdf.set_x(12); pdf.multi_cell(186, 6, ag["tool"])

        y = pdf.get_y() + 5
        lines = ag["prompt"].count("\n") + 1
        box_h = max(40, lines * 6 + 16)
        pdf.set_fill_color(18, 18, 18); pdf.rect(12, y, 186, box_h, "F")
        pdf.set_font("A", "B", 9); pdf.set_text_color(200, 255, 0)
        pdf.set_xy(17, y + 4); pdf.cell(0, 6, "ПРОМПТ:", ln=True)
        pdf.set_font("A", "", 9); pdf.set_text_color(215, 215, 215)
        pdf.set_xy(17, pdf.get_y()); pdf.multi_cell(176, 5, ag["prompt"])

        y2 = y + box_h + 4
        if y2 + 18 < 272:
            pdf.set_fill_color(235, 255, 200); pdf.rect(12, y2, 186, 18, "F")
            pdf.set_font("A", "B", 10); pdf.set_text_color(15, 15, 15)
            pdf.set_xy(17, y2 + 4)
            pdf.multi_cell(176, 6, f">> {ag['result']}")

    # ── CTA ──────────────────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(10, 10, 10); pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(200, 255, 0)
    pdf.rect(0, 0, 210, 7, "F"); pdf.rect(0, 290, 210, 7, "F")

    def mc(text, h=9, bold=False, size=13, color=(255,255,255), dy=0):
        if dy: pdf.set_y(pdf.get_y() + dy)
        pdf.set_x(10)
        pdf.set_font("A", "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(190, h, text, align="C")

    mc("8 АГЕНТОВ ЗАМЕНЯЮТ:", h=11, bold=True, size=22, color=(200,255,0), dy=21)
    mc("SMM-щика  ........  40-80K руб./мес", dy=5)
    mc("Дизайнера  .......  30-60K руб./мес")
    mc("Копирайтера  .....  20-40K руб./мес")
    mc("Аналитика  .......  30-50K руб./мес")

    pdf.set_fill_color(200, 255, 0); pdf.rect(50, pdf.get_y() + 4, 110, 2, "F")
    mc("МОИ РАСХОДЫ: ~500 руб./МЕС", h=10, bold=True, size=17, color=(200,255,0), dy=10)
    mc("Хочешь собрать такую же систему за 7 дней?", h=8, size=12, color=(200,200,200), dy=12)
    mc("TRUE AI ACADEMY\n2 дня БЕСПЛАТНО", h=11, bold=True, size=18, color=(200,255,0), dy=14)
    mc("@Trueman_ai_bot", h=7, size=11, color=(140,140,140), dy=12)

    pdf.output(OUT)
    print(f"PDF готов: {OUT} ({os.path.getsize(OUT):,} байт)")


if __name__ == "__main__":
    build()
