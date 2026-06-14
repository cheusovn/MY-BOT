#!/usr/bin/env python3
"""AI-баннеры: фон рисует nano-banana (через OpenRouter), чёткий текст
накладывает Pillow в фирменном стиле сайта (Unbounded + Manrope, acid-green).

Почему так: image-модели плохо рендерят текст (особенно кириллицу), поэтому
заголовки рисуем сами поверх фона — текст всегда читаемый, фон эффектный.

Стиль повторяет сайт TRUE AI ACADEMY:
  acid-green #C8FF00 · mint #00FF88 · deep black #050604 · text #F2F5EC
  шрифты: Unbounded (заголовки), Manrope (подписи).

Фоны кэшируются в images/_bg/, чтобы менять текст/шрифты без новых запросов к AI.
Перегенерировать фоны: FORCE_BG=1 ... python3 scripts/make_banners_ai.py

Ключ берётся ТОЛЬКО из окружения (никогда не хардкодим, не коммитим):
    OPENROUTER_API_KEY=sk-or-... python3 scripts/make_banners_ai.py

Вывод: images/<name>.jpg (1280x520), welcome.jpg и author.jpg — в корне/images.
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
BG_DIR = os.path.join(OUT_DIR, "_bg")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(BG_DIR, exist_ok=True)

KEY = os.environ.get("OPENROUTER_API_KEY", "")
URL = "https://openrouter.ai/api/v1/chat/completions"
FORCE_BG = os.environ.get("FORCE_BG", "") == "1"
MODELS = [
    os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip(),
    "google/gemini-3.1-flash-image-preview",
    "google/gemini-2.5-flash-image",
]
MODELS = [m for m in MODELS if m]

W, H = 1280, 520
# Палитра сайта (style.css)
ACID = (200, 255, 0)      # #C8FF00
MINT = (0, 255, 136)      # #00FF88
TEXT = (242, 245, 236)    # #F2F5EC
DIM = (170, 180, 163)     # #AAB4A3
DEEP = (5, 6, 4)          # #050604

# Фирменные шрифты сайта (Unbounded/Manrope). Если нет — откат на DejaVu.
FONTS_DIR = os.environ.get("FONTS_DIR", "/tmp/fonts")
UNBOUNDED = os.path.join(FONTS_DIR, "Unbounded-Bold.ttf")
MANROPE = os.path.join(FONTS_DIR, "Manrope.ttf")
DEJA_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJA_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size, bold=True, weight=None):
    """Загружает фирменный шрифт нужного начертания (вариативный wght)."""
    path = UNBOUNDED if bold else MANROPE
    if not os.path.exists(path):
        return ImageFont.truetype(DEJA_B if bold else DEJA_R, size)
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([weight or (800 if bold else 600)])
    except Exception:
        pass
    return f


# ─── AI-фон ──────────────────────────────────────────────────────────────────

def ai_background(theme_prompt: str):
    """Просит nano-banana нарисовать кинематографичную сцену-фон (без текста).

    Сцены — тёплые и уютные (предметы, рабочие столы, мягкий свет, абстракция),
    БЕЗ людей: так баннер выглядит премиально и не вызывает ощущения «сгенерено ботом».
    Левая треть остаётся тёмной — туда ляжет читаемый текст поверх.
    """
    if not KEY:
        return None
    prompt = (
        theme_prompt +
        " Cinematic still-life / product photography, shot on Sony A7R V 50mm, f/1.8 shallow "
        "depth of field, soft natural light with warm acid lime-green (#C8FF00) and mint "
        "(#00FF88) accent glow, deep near-black (#070905) shadows, premium editorial mood, "
        "hyper-detailed, 8k, photorealistic, cozy and inviting atmosphere. "
        "IMPORTANT: absolutely NO people, NO humans, NO faces, NO hands, NO body parts. "
        "Composition: main subject on the RIGHT, keep the LEFT third dark, calm and empty "
        "for text overlay. Absolutely NO text, NO words, NO letters, NO numbers, NO logos, "
        "NO watermarks anywhere in the image. Wide 16:9 cinematic frame."
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


def get_bg(name, theme):
    """Возвращает готовый фон 1280x520. Кэширует AI-фон в images/_bg/<name>.jpg."""
    cache = os.path.join(BG_DIR, f"{name}.jpg")
    if not FORCE_BG and os.path.exists(cache):
        return Image.open(cache).convert("RGB")
    raw = ai_background(theme)
    bg = cover(raw) if raw is not None else gradient_bg()
    try:
        bg.save(cache, "JPEG", quality=92)
    except Exception:
        pass
    return bg


def scrim(img):
    """Тёмная вуаль слева — чтобы текст читался поверх любого фона."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(W):
        a = int(210 * max(0, 1 - x / (W * 0.74)) ** 1.1)
        d.line([(x, 0), (x, H)], fill=(DEEP[0], DEEP[1], DEEP[2], a))
    d.rectangle([0, 0, W, H], fill=(DEEP[0], DEEP[1], DEEP[2], 44))
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


def _fit_title(draw, title, max_w, max_h):
    """Подбирает кегль Unbounded так, чтобы заголовок влез по ширине и высоте."""
    for size in (54, 48, 42, 37, 33):
        f = font(size, weight=800)
        lines = wrap(draw, title, f, max_w)
        step = int(size * 1.16)
        if len(lines) * step <= max_h and len(lines) <= 3:
            return f, lines, step
    f = font(33, weight=800)
    return f, wrap(draw, title, f, max_w), int(33 * 1.16)


def draw_overlay(img, kicker, title, subtitle):
    """Накладывает вордмарк + кикер + заголовок + подпись в стиле сайта."""
    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    # Вордмарк TRUE AI ACADEMY
    wf = font(22, weight=800)
    x, y = 64, 46
    for txt, col in [("TRUE ", TEXT), ("AI", ACID), (" ACADEMY", TEXT)]:
        draw.text((x, y), txt, font=wf, fill=col)
        x += draw.textlength(txt, font=wf)

    left = 64
    # Кикер с подчёркивающей линией
    kf = font(20, weight=700)
    ky = 176
    draw.text((left, ky), kicker.upper(), font=kf, fill=ACID)
    kw = draw.textlength(kicker.upper(), font=kf)
    draw.line([left, ky + 36, left + max(kw, 60), ky + 36], fill=ACID, width=3)

    # Заголовок (авто-подбор кегля)
    top = ky + 60
    tf, lines, step = _fit_title(draw, title, W - left - 150, H - top - 78)
    yy = top
    for ln in lines:
        draw.text((left + 2, yy + 2), ln, font=tf, fill=(0, 0, 0, 170))
        draw.text((left, yy), ln, font=tf, fill=TEXT)
        yy += step

    # Подпись
    if subtitle:
        sf = font(27, bold=False, weight=600)
        for ln in wrap(draw, subtitle, sf, W - left - 150):
            draw.text((left, yy + 10), ln, font=sf, fill=DIM)
            yy += 38

    return img.convert("RGB")


def render(name, kicker, title, subtitle, theme):
    print(f"  → {name}")
    img = scrim(get_bg(name, theme))
    out_img = draw_overlay(img, kicker, title, subtitle)
    out = os.path.join(ROOT if name == "welcome" else OUT_DIR, f"{name}.jpg")
    out_img.save(out, "JPEG", quality=90)
    print(f"    ✓ {out}")


# ─── Баннер автора из реального фото (для доверия) ───────────────────────────

def author_bg(photo_path):
    """Компонует портрет автора справа на фирменном тёмном фоне с зелёным сиянием."""
    canvas = Image.new("RGB", (W, H), DEEP)
    # Мягкое зелёное сияние справа (брендовый акцент)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 720, -240, W + 240, H + 240], fill=(ACID[0], ACID[1], ACID[2], 38))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")

    # Портрет: вписываем в правую область, crop по центру (cover)
    pw, ph = 600, H
    photo = Image.open(photo_path).convert("RGB")
    iw, ih = photo.size
    scale = max(pw / iw, ph / ih)
    photo = photo.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    iw, ih = photo.size
    photo = photo.crop(((iw - pw) // 2, (ih - ph) // 2, (iw - pw) // 2 + pw, (ih - ph) // 2 + ph))

    # Маска с мягким левым краем — портрет «растворяется» в фоне без шва
    mask = Image.new("L", (pw, ph), 0)
    md = ImageDraw.Draw(mask)
    for x in range(pw):
        md.line([(x, 0), (x, ph)], fill=int(255 * min(1.0, x / (pw * 0.42))))
    canvas.paste(photo, (W - pw, 0), mask)
    return scrim(canvas.convert("RGB"))


def render_author():
    print("  → author")
    photo = os.path.join(OUT_DIR, "author.jpg")
    if not os.path.exists(photo):
        print("    ⚠ images/author.jpg нет — пропуск")
        return
    img = author_bg(photo)
    out_img = draw_overlay(
        img,
        "Автор курса",
        "Николай Труман",
        "Основатель TRUE AI ACADEMY · эксперт по нейросетям",
    )
    out = os.path.join(OUT_DIR, "author_card.jpg")
    out_img.save(out, "JPEG", quality=92)
    print(f"    ✓ {out}")


BANNERS = [
    ("day1", "День 1 · бесплатно", "Первые гиперреалистичные фото",
     "Nano Banana 2 и GPT Image 2 — с нуля",
     "A cozy home desk in the evening: an open laptop glowing softly with a freshly created "
     "AI artwork on its screen, a warm desk lamp, a steaming mug of tea, an open notebook "
     "and pen, a small plant, calm homely atmosphere, the quiet joy of a first success."),
    ("day2", "День 2 · бесплатно", "Промпты и GPT Image 2",
     "Пишем запросы, которые дают результат",
     "A clean modern desk: a laptop screen showing polished product photos and a freelance "
     "order confirmation, a smartphone with a payment notification beside it, a cup of "
     "coffee, soft green accent light, evening city softly blurred through the window."),
    ("day3", "День 3 · курс", "Персонажи и сториборды",
     "Придумываем героев и раскадровки с ИИ",
     "A creative desk still life: a tablet and monitor showing a character design concept "
     "sheet and a row of storyboard sketch frames, colored pencils and notes nearby, "
     "concept-art studio vibe, warm green accent glow, no real people."),
    ("day4", "День 4 · курс", "Анимация и движение камеры",
     "Оживляем кадры и правим фото",
     "A creator desk: a wide monitor showing a video animation timeline with motion-path "
     "curves and a before/after photo retouch, a small camera slider and gimbal on the desk, "
     "dynamic motion feel, warm green accent glow, no people."),
    ("day5", "День 5 · курс", "Звук и видео — Suno и Kling",
     "Музыка, песни и ролики нейросетью",
     "A cozy home studio still life: a condenser microphone and headphones, one screen with "
     "a glowing audio waveform and music timeline, another screen with vivid video clip "
     "frames, soft warm light with green accents, no people."),
    ("day6", "День 6 · курс", "Создаём кино — Seedance 2.0",
     "Снимаем настоящий фильм нейросетью",
     "A cinematic still on a wide monitor showing a dramatic film frame, a clapperboard and "
     "subtle film-reel motifs on a dark desk, moody movie-making atmosphere, soft green "
     "accent glow, no people."),
    ("day7", "День 7 · курс", "Цифровой аватар и GPT-агенты",
     "Свой аватар и умные ассистенты",
     "A futuristic but cozy desk: a screen showing a glowing stylized 3D digital avatar bust "
     "and floating chat-bot agent UI bubbles around it, premium tech feel, acid-green and "
     "mint glow, abstract avatar with no real human face, no people."),
    ("day8", "День 8 · бонус", "Продвижение и продажи",
     "SMM, маркетинг и поток клиентов",
     "A dark premium dashboard still life: a rising growth chart on a screen with floating "
     "glowing social engagement icons (likes, arrows up) around it, dynamic successful "
     "marketing vibe, acid-green and mint glow, no text on the icons, no people."),
    ("tariffs", "Тарифы", "Выбери, как удобно учиться",
     "Оплатил один раз — доступ остаётся навсегда",
     "Three sleek premium dark glass cards floating in soft studio light, the middle one "
     "taller and highlighted with a warm green glow, minimal luxury product-shot aesthetic, "
     "elegant and trustworthy."),
    ("special", "Только для своих", "Лучшая цена и бонусы",
     "Ты дошёл до конца — это правда редкость",
     "A softly glowing premium dark gift box opening on its own, gentle green-gold light "
     "spilling out from inside, a few sparkles floating up, intimate close-up still life, "
     "the feeling of a genuine well-earned reward."),
    ("gift", "Подарок", "100+ нейросетей — бесплатно",
     "Midjourney, ChatGPT, Suno и ещё 95+",
     "An open premium dark gift box with many small softly glowing rounded app-like icons "
     "rising out of it like fireflies, sense of abundance and generosity, warm green glow, "
     "clean minimal still life, no symbols or text on the icons."),
    ("results", "Истории", "Начинали с нуля — как ты",
     "Дальше — твоя история",
     "A cozy table by a window: a smartphone propped up showing a cheerful success "
     "notification, a cup of coffee, a small plant and an open notebook, warm soft daylight "
     "with a gentle green accent, relatable everyday atmosphere, the feeling of a small win."),
    ("wheel", "Колесо удачи", "Один бесплатный прокрут",
     "Скидки, промпты и месяц с куратором",
     "A playful spinning prize wheel made of soft glowing light with gentle motion blur, "
     "festive friendly energy, warm green and mint highlights on a dark background, "
     "fun but premium, abstract, no text on the wheel."),
    ("wow", "Минута магии", "Оживи своё фото",
     "Пришли кадр — покажу, на что способна нейросеть",
     "A blank instant Polaroid-style photo frame on a dark surface, magically filling with "
     "vivid colorful artwork that bursts out as paint-like light streaks and sparkles, "
     "sense of wonder and transformation, warm green magical glow, clean and tasteful, "
     "no people or faces in the artwork."),
    ("welcome", "Добро пожаловать", "Нейросети — проще, чем кажется",
     "Первые 2 дня курса — бесплатно, без карты",
     "A cozy warm home table in the evening: a smartphone showing a friendly softly glowing "
     "screen, a mug of tea, a small plant and a soft blanket nearby, gentle inviting light "
     "with a subtle green glow, welcoming atmosphere, the feeling of an easy first step."),
]


def main():
    if not KEY:
        print("⚠️  OPENROUTER_API_KEY не задан — будут брендовые градиенты без AI-фона.")
    print(f"Генерирую баннеры в {OUT_DIR} (шрифты сайта: Unbounded + Manrope)…")
    for spec in BANNERS:
        render(*spec)
    render_author()
    print("Готово.")


if __name__ == "__main__":
    main()
