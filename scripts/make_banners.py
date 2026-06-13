#!/usr/bin/env python3
"""Генератор брендовых шапок-баннеров для экранов бота.

Стиль бренда True AI Academy: acid-green (#C8FF00) на тёмном (#070905).
Без эмодзи в самой картинке (в Pillow нет цветного emoji-шрифта — они бы
рендерились «квадратами»), только типографика + геометрия.

Запуск:  python3 scripts/make_banners.py
Вывод:   images/<name>.jpg  (1280x520, под Telegram answer_photo)

Перегенерировать в любой момент — просто запустить снова.
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "images")
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 1280, 520
ACID = (200, 255, 0)
ACID_SOFT = (220, 255, 94)
MINT = (0, 255, 136)
TEXT = (242, 245, 236)
DIM = (150, 165, 140)
FAINT = (110, 125, 110)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size, bold=True):
    return ImageFont.truetype(FONT_PATH if bold else FONT_REG, size)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def bg_gradient(img):
    """Вертикальный градиент тёмный → чуть светлее сверху."""
    top = (12, 15, 9)
    bot = (5, 6, 4)
    px = img.load()
    for y in range(H):
        t = y / H
        col = lerp(top, bot, t)
        for x in range(W):
            px[x, y] = col


def dot_grid(draw):
    """Тонкая точечная сетка — «техно» подложка."""
    step = 36
    for y in range(40, H, step):
        for x in range(40, W, step):
            draw.ellipse([x, y, x + 2, y + 2], fill=(255, 255, 255, 8))


def acid_glow(img, cx, cy, r=320, color=ACID, alpha=46):
    """Радиальное свечение бренд-цветом в углу."""
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(r, 0, -4):
        a = int(alpha * (1 - i / r) ** 2)
        gd.ellipse([cx - i, cy - i, cx + i, cy + i], fill=color + (a,))
    img.alpha_composite(glow)


def wordmark(draw):
    """Лого-вордмарк сверху: TRUE AI ACADEMY (AI — acid)."""
    f = font(26)
    x, y = 64, 50
    parts = [("TRUE ", TEXT), ("AI", ACID), (" ACADEMY", TEXT)]
    for txt, col in parts:
        draw.text((x, y), txt, font=f, fill=col)
        x += draw.textlength(txt, font=f)


def wrap(draw, text, f, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=f) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make(name, kicker, title, subtitle, big=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    bg_gradient(img)
    acid_glow(img, W - 80, -40, r=380, color=ACID, alpha=40)
    acid_glow(img, -60, H + 40, r=320, color=MINT, alpha=26)

    draw = ImageDraw.Draw(img, "RGBA")
    dot_grid(draw)
    wordmark(draw)

    # Полупрозрачное «слово-якорь» справа (например, номер дня)
    if big:
        bf = font(300)
        bw = draw.textlength(big, font=bf)
        draw.text((W - bw - 30, H - 360), big, font=bf, fill=ACID + (22,))

    left = 64
    # Kicker (мелкая надпись над заголовком, acid)
    kf = font(26)
    ky = 188
    draw.text((left, ky), kicker.upper(), font=kf, fill=ACID)
    kw = draw.textlength(kicker.upper(), font=kf)
    draw.line([left, ky + 40, left + max(kw, 60), ky + 40], fill=ACID, width=3)

    # Заголовок (крупный, с переносами)
    tf = font(66)
    lines = wrap(draw, title, tf, W - left - 360 if big else W - left - 120)
    y = ky + 66
    for ln in lines:
        draw.text((left, y), ln, font=tf, fill=TEXT)
        y += 78

    # Подзаголовок
    if subtitle:
        sf = font(30, bold=False)
        for ln in wrap(draw, subtitle, sf, W - left - 360 if big else W - left - 120):
            draw.text((left, y + 8), ln, font=sf, fill=DIM)
            y += 40

    out = os.path.join(OUT_DIR, f"{name}.jpg")
    img.convert("RGB").save(out, "JPEG", quality=88)
    print(f"  ✓ {out}")


BANNERS = [
    ("day1",    "День 1 · бесплатно",   "Первый AI-результат за 40 минут",
     "Запусти нейросеть и напиши первый рабочий промпт", "1"),
    ("day2",    "День 2 · бесплатно",   "Где в AI лежат деньги",
     "Работы, за которые платят. Навык → заказ → доход", "2"),
    ("tariffs", "Тарифы обучения",      "Выбери свой доступ",
     "Один раз — и материалы остаются навсегда", None),
    ("special", "Закрытое предложение", "Только для дошедших до конца",
     "Лучшая цена и бонусы — действуют ограниченное время", None),
    ("gift",    "Подарок",              "100+ нейросетей бесплатно",
     "Midjourney, ChatGPT, Kling, Suno и ещё 95+ — на 100+ дней", None),
    ("results", "Результаты",           "347 выпускников за полгода",
     "Они начинали с нуля. Следующий кейс — твой", None),
    ("wheel",   "Колесо удачи",         "Один бесплатный прокрут",
     "Скидки, промпты, гайды и месяц VIP-куратора", None),
    ("wow",     "AI-чудо за минуту",    "Оживи своё фото нейросетью",
     "Пришли кадр — увидишь, что это проще, чем кажется", None),
]


def main():
    print(f"Генерирую баннеры в {OUT_DIR} …")
    for spec in BANNERS:
        make(*spec)
    print("Готово.")


if __name__ == "__main__":
    main()
