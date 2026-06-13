#!/usr/bin/env python3
"""AI-баннеры: фон рисует nano-banana (через OpenRouter), чёткий текст
накладывает Pillow.

Почему так: image-модели плохо рендерят текст (особенно кириллицу), поэтому
заголовки рисуем сами поверх AI-фона — текст всегда читаемый, фон эффектный.

Ключ берётся ТОЛЬКО из окружения (никогда не хардкодим, не коммитим):
    OPENROUTER_API_KEY=sk-or-... python3 scripts/make_banners_ai.py

Вывод: images/<name>.jpg (1280x520). Если AI-фон не сгенерился —
откатывается к брендовому градиенту (как в make_banners.py).
"""
import os
import io
import json
import time
import base64
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "images")
os.makedirs(OUT_DIR, exist_ok=True)

KEY = os.environ.get("OPENROUTER_API_KEY", "")
URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [
    os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip(),
    "google/gemini-3.1-flash-image-preview",
    "google/gemini-2.5-flash-image",
    "google/gemini-2.5-flash-image-preview",
]
MODELS = [m for m in MODELS if m]

W, H = 1280, 520
ACID = (200, 255, 0)
TEXT = (245, 248, 238)
DIM = (165, 178, 158)
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size, bold=True):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def ai_background(theme_prompt: str):
    """Просит nano-banana нарисовать абстрактный брендовый фон (без текста)."""
    if not KEY:
        return None
    prompt = (
        "Abstract futuristic background, deep near-black (#070905) with vivid "
        "acid lime-green (#C8FF00) and mint glowing accents, soft gradient mesh, "
        "subtle tech grid and particles, cinematic depth, premium AI aesthetic. "
        + theme_prompt +
        " IMPORTANT: absolutely NO text, NO words, NO letters, NO numbers, "
        "NO logos. Leave the left half darker and calmer for text overlay. "
        "Wide 16:9 composition."
    )
    payload = {
        "model": None,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "modalities": ["image", "text"],
    }
    for model in MODELS:
        payload["model"] = model
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(URL, data=data, headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/Trueman_ai_bot",
            "X-Title": "True AI Academy",
        })
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            msg = body["choices"][0]["message"]
            for im in (msg.get("images") or []):
                url = (im.get("image_url") or {}).get("url", "")
                if url.startswith("data:"):
                    b64 = url.split(",", 1)[1]
                    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
                    print(f"    bg via {model}")
                    return img
            print(f"    {model}: нет картинки → следующая модель")
        except Exception as e:
            print(f"    {model} ошибка: {e} → следующая модель")
        time.sleep(1)
    return None


def gradient_bg():
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        col = (int(12 - 7 * t), int(15 - 9 * t), int(9 - 5 * t))
        for x in range(W):
            px[x, y] = col
    return img


def cover(img):
    """Масштабирует фон под 1280x520 (crop по центру)."""
    iw, ih = img.size
    scale = max(W / iw, H / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    iw, ih = img.size
    return img.crop(((iw - W) // 2, (ih - H) // 2, (iw - W) // 2 + W, (ih - H) // 2 + H))


def scrim(img):
    """Тёмная вуаль слева — чтобы текст читался поверх любого фона."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(W):
        a = int(205 * max(0, 1 - x / (W * 0.72)) ** 1.1)
        d.line([(x, 0), (x, H)], fill=(4, 6, 4, a))
    d.rectangle([0, 0, W, H], fill=(4, 6, 4, 40))
    return Image.alpha_composite(img.convert("RGBA"), ov)


def wrap(draw, text, f, max_w):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= max_w:
            cur = t
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def render(name, kicker, title, subtitle, theme):
    print(f"  → {name}")
    bg = ai_background(theme) or gradient_bg()
    img = scrim(cover(bg))
    draw = ImageDraw.Draw(img, "RGBA")

    # Вордмарк
    f = font(26)
    x, y = 64, 48
    for txt, col in [("TRUE ", TEXT), ("AI", ACID), (" ACADEMY", TEXT)]:
        draw.text((x, y), txt, font=f, fill=col)
        x += draw.textlength(txt, font=f)

    left = 64
    kf = font(26)
    ky = 184
    draw.text((left, ky), kicker.upper(), font=kf, fill=ACID)
    kw = draw.textlength(kicker.upper(), font=kf)
    draw.line([left, ky + 40, left + max(kw, 60), ky + 40], fill=ACID, width=3)

    tf = font(64)
    yy = ky + 64
    for ln in wrap(draw, title, tf, W - left - 140):
        # лёгкая тень для читаемости
        draw.text((left + 2, yy + 2), ln, font=tf, fill=(0, 0, 0, 160))
        draw.text((left, yy), ln, font=tf, fill=TEXT)
        yy += 76
    if subtitle:
        sf = font(30, bold=False)
        for ln in wrap(draw, subtitle, sf, W - left - 140):
            draw.text((left, yy + 8), ln, font=sf, fill=DIM)
            yy += 40

    out = os.path.join(OUT_DIR, f"{name}.jpg")
    img.convert("RGB").save(out, "JPEG", quality=88)
    print(f"    ✓ {out}")


BANNERS = [
    ("day1", "День 1 · бесплатно", "Первый AI-результат за 40 минут",
     "Запусти нейросеть и напиши первый рабочий промпт",
     "Glowing neural spark igniting, beginning of a journey, sunrise energy."),
    ("day2", "День 2 · бесплатно", "Где в AI лежат деньги",
     "Работы, за которые платят. Навык → заказ → доход",
     "Flowing green currency-like light streams and rising graph energy."),
    ("tariffs", "Тарифы обучения", "Выбери свой доступ",
     "Один раз — и материалы остаются навсегда",
     "Three glowing vertical light pillars of different height, premium."),
    ("special", "Закрытое предложение", "Только для дошедших до конца",
     "Лучшая цена и бонусы — действуют ограниченное время",
     "Exclusive vault of light opening, golden-green premium glow, VIP."),
    ("gift", "Подарок", "100+ нейросетей бесплатно",
     "Midjourney, ChatGPT, Kling, Suno и ещё 95+ — на 100+ дней",
     "Burst of many small glowing app-like nodes, abundance, gift energy."),
    ("results", "Результаты", "347 выпускников за полгода",
     "Они начинали с нуля. Следующий кейс — твой",
     "Constellation of connected glowing dots forming a rising network."),
    ("wheel", "Колесо удачи", "Один бесплатный прокрут",
     "Скидки, промпты, гайды и месяц VIP-куратора",
     "Spinning radial light wheel, motion blur, playful lucky energy."),
    ("wow", "AI-чудо за минуту", "Оживи своё фото нейросетью",
     "Пришли кадр — увидишь, что это проще, чем кажется",
     "Magic transformation sparkles around a glowing portrait frame."),
]


def main():
    if not KEY:
        print("⚠️  OPENROUTER_API_KEY не задан — будут брендовые градиенты без AI-фона.")
    print(f"Генерирую AI-баннеры в {OUT_DIR} …")
    for spec in BANNERS:
        render(*spec)
    print("Готово.")


if __name__ == "__main__":
    main()
