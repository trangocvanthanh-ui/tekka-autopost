"""Render a 1080x1920 Story poster from a product photo."""
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 250, 340  # areas covered by the Story UI
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
_EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿️‍]")


def _font(weight: str, size: int):
    return ImageFont.truetype(str(FONT_DIR / f"Poppins-{weight}.ttf"), size)


def strip_emoji(text: str) -> str:
    return re.sub(r"\s+", " ", _EMOJI.sub("", text)).strip()


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, weight, start, min_size, max_w, max_lines):
    """Largest font size whose wrapped text fits within max_lines."""
    size = start
    while size >= min_size:
        f = _font(weight, size)
        lines = _wrap(draw, text, f, max_w)
        if len(lines) <= max_lines and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 2
    f = _font(weight, min_size)
    lines = _wrap(draw, text, f, max_w)[:max_lines]
    if lines and len(_wrap(draw, text, f, max_w)) > max_lines:
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return f, lines


def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return m


def display_link(url: str) -> str:
    """'https://www.tekkashop.com.my/x' -> 'tekkashop.com.my/x' (what we print on the poster)."""
    u = re.sub(r"^https?://", "", (url or "").strip(), flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I)
    return u.rstrip("/")


def build_poster(image_bytes: bytes, name: str, price: str, hook: str, cfg: dict,
                 short_url: str = "") -> Image.Image:
    c = cfg["colors"]
    img = Image.new("RGB", (W, H), c["background"])
    d = ImageDraw.Draw(img)
    margin = 80
    inner_w = W - 2 * margin

    # brand wordmark
    brand_f = _font("Medium", 34)
    brand = " ".join(cfg["shop_name"].upper())
    d.text((W / 2, SAFE_TOP + 10), brand, font=brand_f, fill=c["muted"], anchor="mt")
    y = SAFE_TOP + 80

    # hook
    hook_f, hook_lines = _fit(d, strip_emoji(hook), "Bold", 78, 52, inner_w, 3)
    lh = int(hook_f.size * 1.22)
    for line in hook_lines:
        d.text((W / 2, y), line, font=hook_f, fill=c["text"], anchor="mt")
        y += lh
    y += 30

    # reserve space for name + price/cta
    name_f, name_lines = _fit(d, name, "Medium", 44, 34, inner_w, 2) if name else (None, [])
    name_h = int(name_f.size * 1.3) * len(name_lines) if name_lines else 0
    link_txt = display_link(short_url)
    link_h = 24 + 46 if link_txt else 0
    bottom_block = (name_h + 24 if name_h else 0) + 96 + 28 + 96 + link_h
    card_bottom = H - SAFE_BOTTOM - bottom_block
    card_h = max(card_bottom - y, 400)
    card_w = inner_w

    # product card (contain, never crop the product)
    card = Image.new("RGB", (card_w, card_h), c["card"])
    prod = Image.open(io.BytesIO(image_bytes))
    prod = ImageOps.exif_transpose(prod)
    if prod.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", prod.size, c["card"])
        prod = prod.convert("RGBA")
        bg.paste(prod, mask=prod.split()[-1])
        prod = bg
    else:
        prod = prod.convert("RGB")
    pad = 36
    prod.thumbnail((card_w - 2 * pad, card_h - 2 * pad), Image.LANCZOS)
    card.paste(prod, ((card_w - prod.width) // 2, (card_h - prod.height) // 2))

    shadow = Image.new("RGBA", (card_w + 120, card_h + 120), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((60, 70, card_w + 60, card_h + 70), 48, fill=(0, 0, 0, 45))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    img.paste(shadow, (margin - 60, y - 60), shadow)
    img.paste(card, (margin, y), _rounded_mask((card_w, card_h), 48))
    y += card_h + 36

    # product name
    if name_lines:
        nl = int(name_f.size * 1.3)
        for line in name_lines:
            d.text((W / 2, y), line, font=name_f, fill=c["text"], anchor="mt")
            y += nl
        y += 24

    # price pill
    if price:
        pf = _font("Bold", 54)
        tw = d.textlength(price, font=pf)
        pw, ph = int(tw + 90), 96
        x0 = (W - pw) // 2
        d.rounded_rectangle((x0, y, x0 + pw, y + ph), ph // 2, fill=c["price_bg"])
        d.text((W / 2, y + ph / 2), price, font=pf, fill=c["text"], anchor="mm")
    y += 96 + 28

    # CTA
    cf = _font("Medium", 40)
    cta = cfg.get("cta_text_with_link", "Shop now") if link_txt else cfg["cta_text"]
    tw = d.textlength(cta, font=cf)
    cw, ch = int(tw + 110), 96
    x0 = (W - cw) // 2
    d.rounded_rectangle((x0, y, x0 + cw, y + ch), ch // 2, fill=c["accent"])
    d.text((W / 2, y + ch / 2), cta, font=cf, fill=c["accent_text"], anchor="mm")
    y += ch + 24

    # short link (plain text, customers type or search it: Story API has no link sticker)
    if link_txt:
        lf, lines = _fit(d, link_txt, "Medium", 38, 24, inner_w, 1)
        d.text((W / 2, y), lines[0] if lines else link_txt, font=lf, fill=c["text"], anchor="mt")
    return img


def save_jpeg(img: Image.Image, path) -> None:
    img.save(path, "JPEG", quality=92, optimize=True)
