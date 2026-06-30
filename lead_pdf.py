"""Lead magnet PDF generator — 8 AI-агентов для Instagram."""
import os
import logging
import urllib.request

_DIR = os.path.dirname(__file__)
LEAD_PDF_PATH = os.path.join(_DIR, "lead_magnet.pdf")
_FONT_REGULAR = os.path.join(_DIR, "DejaVuSans.ttf")
_FONT_BOLD = os.path.join(_DIR, "DejaVuSans-Bold.ttf")

# System font search paths (Ubuntu/Debian/Alpine — Amvera)
_SYS_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]
_SYS_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]

_FONT_URLS = {
    _FONT_REGULAR: [
        "https://cdn.jsdelivr.net/gh/dejavu-fonts/dejavu-fonts@master/ttf/DejaVuSans.ttf",
        "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf",
    ],
    _FONT_BOLD: [
        "https://cdn.jsdelivr.net/gh/dejavu-fonts/dejavu-fonts@master/ttf/DejaVuSans-Bold.ttf",
        "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans-Bold.ttf",
    ],
}

AGENTS = [
    {
        "num": "01", "name": "АНАЛИТИК",
        "what": "Каждый понедельник в 9:00 собирает недельный отчёт: охваты, показы, лучшие и худшие посты.",
        "tool": "Instagram Graph API + OpenRouter (GPT-4o-mini)",
        "prompt": (
            "Проанализируй метрики Instagram за неделю: [данные]\n"
            "Выдели: топ-3 поста по охвату, худший пост и почему,\n"
            "рекомендации на следующую неделю.\n"
            "Формат: таблица + 3 вывода."
        ),
        "result": "0 минут на аналитику. Точно знаю что работает.",
    },
    {
        "num": "02", "name": "ОХОТНИК ЗА ТРЕНДАМИ",
        "what": "Ищет вирусные темы в нише AI каждое утро -- что набирает просмотры у конкурентов.",
        "tool": "DuckDuckGo Search API + Claude Sonnet",
        "prompt": (
            "Найди 5 трендовых тем в нише 'AI для бизнеса' за последние 3 дня.\n"
            "Для каждой: заголовок, почему вирусная, идея поста для Instagram.\n"
            "Фокус: предприниматели, которые хотят экономить время."
        ),
        "result": "Контент-план готов за 5 минут вместо 2 часов.",
    },
    {
        "num": "03", "name": "ШПИОН ЗА КОНКУРЕНТАМИ",
        "what": "Мониторит топ-5 конкурентов и находит их залетевшие посты для адаптации.",
        "tool": "Meta Graph API + OpenRouter",
        "prompt": (
            "Проанализируй этот пост конкурента с высоким ER: [текст]\n"
            "Что сделало его виральным? Хук, структура, CTA.\n"
            "Предложи 3 варианта похожего поста для моей ниши."
        ),
        "result": "Беру лучшее у конкурентов и адаптирую под себя.",
    },
    {
        "num": "04", "name": "КОПИРАЙТЕР",
        "what": "Пишет хуки, описания и хештеги под каждый пост за 30 секунд.",
        "tool": "Claude Sonnet через OpenRouter",
        "prompt": (
            "Напиши 5 хуков для Instagram-поста.\n"
            "Тема: [тема]. Ниша: нейросети и AI для бизнеса.\n"
            "Аудитория: предприниматели 25-40 лет. Стиль: дерзкий.\n"
            "Пример: 'Твой SMM-щик стоит 60 000 руб. Мой -- 0 руб.'"
        ),
        "result": "120+ хуков за месяц. Лучшие дали x3 к охватам.",
    },
    {
        "num": "05", "name": "ПЛАНИРОВЩИК",
        "what": "Составляет контент-план на 30 дней с темами, форматами и временем публикации.",
        "tool": "Claude Sonnet + данные аналитики",
        "prompt": (
            "Составь контент-план на 30 дней для Instagram.\n"
            "Ниша: AI-инструменты для бизнеса. Цель: рост + прогрев к курсу.\n"
            "Форматы: карусели 60%, Reels 30%, Stories 10%.\n"
            "Для каждого: тема, формат, хук, лучшее время."
        ),
        "result": "Месяц контента за 20 минут. Без творческого кризиса.",
    },
    {
        "num": "06", "name": "ДИЗАЙНЕР КАРУСЕЛЕЙ",
        "what": "Создаёт слайды карусели по референсу. 10 слайдов за 10 минут и 70 руб.",
        "tool": "Nano Banana 2 (Gemini 3.1) через OpenRouter",
        "prompt": (
            "Instagram carousel slide 1080x1350.\n"
            "Style: reference image. Black bg #0a0a0a,\n"
            "lime accent #c8ff00, bold condensed font.\n"
            "Title: [ЗАГОЛОВОК НА РУССКОМ]\n"
            "Elements: 3D mockup, glass cards, glow effect."
        ),
        "result": "Дизайнер берёт 5-15K руб. Агент -- 7 руб. за слайд.",
    },
    {
        "num": "07", "name": "ВОРОНКА ПРОДАЖ",
        "what": "Автоматически отвечает на кодовое слово в комментах и ведёт к покупке курса.",
        "tool": "Meta Webhook + Telegram Bot (aiogram)",
        "prompt": (
            "Схема воронки:\n"
            "Карусель -> CTA 'пиши АГЕНТЫ' -> автоответ в комменте\n"
            "-> DM со ссылкой -> Telegram-бот -> подписка канала\n"
            "-> лид-магнит -> 2 дня бесплатно -> продажа"
        ),
        "result": "Конверсия 3-5% от комментария до покупки. Работает 24/7.",
    },
    {
        "num": "08", "name": "ПУБЛИКАТОР",
        "what": "Публикует контент одновременно в Instagram, Threads и Facebook по расписанию.",
        "tool": "Meta Graph API + cron-расписание",
        "prompt": (
            "Расписание публикаций:\n"
            "Вт, Чт, Пт -- карусели в 10:00 и 18:00\n"
            "Ежедневно -- Stories в 12:00\n"
            "Пн, Ср, Вс -- Reels в 19:00"
        ),
        "result": "Три площадки покрыты. Не думаю когда публиковать.",
    },
]


def _find_system_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _ensure_fonts():
    import shutil
    pairs = [
        (_FONT_REGULAR, _SYS_REGULAR_CANDIDATES, _FONT_URLS[_FONT_REGULAR]),
        (_FONT_BOLD,    _SYS_BOLD_CANDIDATES,    _FONT_URLS[_FONT_BOLD]),
    ]
    for local, sys_candidates, urls in pairs:
        if os.path.exists(local):
            continue
        sys_font = _find_system_font(sys_candidates)
        if sys_font:
            shutil.copy(sys_font, local)
            logging.info(f"Скопирован системный шрифт: {sys_font}")
            continue
        for url in urls:
            try:
                logging.info(f"Скачиваю шрифт: {url}")
                urllib.request.urlretrieve(url, local)
                if os.path.getsize(local) > 100_000:
                    break
                os.remove(local)
            except Exception as e:
                logging.warning(f"Не удалось скачать {url}: {e}")


def generate() -> str:
    """Генерирует PDF лид-магнита. Возвращает путь к файлу."""
    if os.path.exists(LEAD_PDF_PATH):
        return LEAD_PDF_PATH

    _ensure_fonts()

    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_font("Reg", "", _FONT_REGULAR)
    pdf.add_font("Reg", "B", _FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Обложка ─────────────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(10, 10, 10)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_fill_color(200, 255, 0)
    pdf.rect(0, 0, 210, 7, "F")
    pdf.rect(0, 290, 210, 7, "F")

    pdf.set_font("Reg", "B", 30)
    pdf.set_text_color(200, 255, 0)
    pdf.set_y(35)
    pdf.multi_cell(0, 13, "8 НЕЙРОСЕТЕЙ\nКОТОРЫЕ ВЕДУТ\nМОЙ INSTAGRAM", align="C")

    pdf.set_font("Reg", "", 15)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(125)
    pdf.multi_cell(0, 9, "На автопилоте. Без команды.\nБез бюджета. Только AI.", align="C")

    pdf.set_font("Reg", "", 13)
    pdf.set_text_color(200, 255, 0)
    pdf.set_y(165)
    pdf.multi_cell(0, 8, "Инструменты + Промпты + Схемы", align="C")

    pdf.set_font("Reg", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.set_y(240)
    pdf.multi_cell(0, 7, "by @nikolay_cheusov  |  TRUE AI ACADEMY", align="C")

    # ── Слайды агентов ──────────────────────────────────────────────────────────
    for ag in AGENTS:
        pdf.add_page()
        pdf.set_fill_color(248, 248, 248)
        pdf.rect(0, 0, 210, 297, "F")

        # Левая лайм-полоса
        pdf.set_fill_color(200, 255, 0)
        pdf.rect(0, 0, 5, 297, "F")

        # Номер (фоновый)
        pdf.set_font("Reg", "B", 52)
        pdf.set_text_color(225, 225, 225)
        pdf.set_xy(12, 8)
        pdf.cell(30, 20, ag["num"])

        # Заголовок агента
        pdf.set_font("Reg", "B", 18)
        pdf.set_text_color(15, 15, 15)
        pdf.set_xy(12, 26)
        pdf.multi_cell(186, 9, f"АГЕНТ {ag['num']}: {ag['name']}")

        # Разделитель
        pdf.set_fill_color(200, 255, 0)
        pdf.rect(12, pdf.get_y() + 1, 186, 2, "F")

        # ЧТО ДЕЛАЕТ
        y = pdf.get_y() + 7
        pdf.set_font("Reg", "B", 9)
        pdf.set_text_color(130, 130, 130)
        pdf.set_xy(12, y)
        pdf.cell(0, 6, "ЧТО ДЕЛАЕТ:", ln=True)
        pdf.set_font("Reg", "", 11)
        pdf.set_text_color(15, 15, 15)
        pdf.set_x(12)
        pdf.multi_cell(186, 6, ag["what"])

        # ИНСТРУМЕНТ
        pdf.set_y(pdf.get_y() + 4)
        pdf.set_font("Reg", "B", 9)
        pdf.set_text_color(130, 130, 130)
        pdf.set_x(12)
        pdf.cell(0, 6, "ИНСТРУМЕНТ:", ln=True)
        pdf.set_font("Reg", "", 11)
        pdf.set_text_color(15, 15, 15)
        pdf.set_x(12)
        pdf.multi_cell(186, 6, ag["tool"])

        # ПРОМПТ (тёмный блок)
        y = pdf.get_y() + 6
        pdf.set_fill_color(18, 18, 18)
        prompt_lines = ag["prompt"].count("\n") + 1
        box_h = max(42, prompt_lines * 6 + 18)
        pdf.rect(12, y, 186, box_h, "F")
        pdf.set_font("Reg", "B", 9)
        pdf.set_text_color(200, 255, 0)
        pdf.set_xy(17, y + 5)
        pdf.cell(0, 6, "ПРОМПТ:", ln=True)
        pdf.set_font("Reg", "", 9)
        pdf.set_text_color(215, 215, 215)
        pdf.set_xy(17, pdf.get_y())
        pdf.multi_cell(176, 5.5, ag["prompt"])

        # РЕЗУЛЬТАТ
        y2 = y + box_h + 5
        if y2 + 20 < 270:
            pdf.set_fill_color(235, 255, 200)
            pdf.rect(12, y2, 186, 20, "F")
            pdf.set_font("Reg", "B", 10)
            pdf.set_text_color(15, 15, 15)
            pdf.set_xy(17, y2 + 5)
            pdf.multi_cell(176, 6, f">> {ag['result']}")

    # ── Финальный CTA ────────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(10, 10, 10)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(200, 255, 0)
    pdf.rect(0, 0, 210, 7, "F")
    pdf.rect(0, 290, 210, 7, "F")

    pdf.set_font("Reg", "B", 20)
    pdf.set_text_color(200, 255, 0)
    pdf.set_y(25)
    pdf.multi_cell(0, 11, "8 АГЕНТОВ ЗАМЕНЯЮТ:", align="C")

    pdf.set_font("Reg", "", 13)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(50)
    for line in [
        "SMM-щика  ....................  40–80K руб./мес",
        "Дизайнера  ...................  30–60K руб./мес",
        "Копирайтера  .................  20–40K руб./мес",
        "Аналитика  ...................  30–50K руб./мес",
    ]:
        pdf.multi_cell(0, 9, line, align="C")

    pdf.set_fill_color(200, 255, 0)
    pdf.rect(50, pdf.get_y() + 4, 110, 2, "F")

    pdf.set_font("Reg", "B", 16)
    pdf.set_text_color(200, 255, 0)
    pdf.set_y(pdf.get_y() + 10)
    pdf.multi_cell(0, 10, "МОИ РАСХОДЫ: ~500 руб./МЕС", align="C")

    pdf.set_font("Reg", "", 12)
    pdf.set_text_color(200, 200, 200)
    pdf.set_y(pdf.get_y() + 12)
    pdf.multi_cell(0, 8, "Хочешь собрать такую же систему?\nЗа 7 дней — от нуля до результата.", align="C")

    pdf.set_font("Reg", "B", 17)
    pdf.set_text_color(200, 255, 0)
    pdf.set_y(pdf.get_y() + 16)
    pdf.multi_cell(0, 11, "TRUE AI ACADEMY\nПервые 2 дня — БЕСПЛАТНО", align="C")

    pdf.set_font("Reg", "", 11)
    pdf.set_text_color(140, 140, 140)
    pdf.set_y(pdf.get_y() + 12)
    pdf.multi_cell(0, 7, "@Trueman_ai_bot", align="C")

    pdf.output(LEAD_PDF_PATH)
    logging.info(f"PDF лид-магнит создан: {LEAD_PDF_PATH}")
    return LEAD_PDF_PATH
