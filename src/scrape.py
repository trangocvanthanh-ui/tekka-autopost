"""Pull name / price / image from a product page (JSON-LD first, Open Graph fallback)."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.ldjson, self._in_ld, self._buf = {}, [], False, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = a.get("property") or a.get("name") or a.get("itemprop")
            if key and a.get("content"):
                self.meta.setdefault(key.lower(), a["content"])
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_ld, self._buf = True, []

    def handle_data(self, data):
        if self._in_ld:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self._in_ld = False
            self.ldjson.append("".join(self._buf))


def _walk(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        yield node
        for v in node.values():
            if isinstance(v, (list, dict)):
                yield from _walk(v)


def _first_image(img):
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, dict):
        img = img.get("url") or img.get("contentUrl")
    return img if isinstance(img, str) else None


def _price_from_offers(offers):
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None, None
    price = offers.get("price") or offers.get("lowPrice")
    if price is None and isinstance(offers.get("priceSpecification"), dict):
        price = offers["priceSpecification"].get("price")
    return price, offers.get("priceCurrency")


def parse_product_html(html: str, base_url: str) -> dict:
    p = _Parser()
    p.feed(html)
    out = {"name": None, "price": None, "currency": None, "image_url": None}

    for blob in p.ldjson:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for node in _walk(data):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" in types:
                out["name"] = out["name"] or node.get("name")
                out["image_url"] = out["image_url"] or _first_image(node.get("image"))
                price, cur = _price_from_offers(node.get("offers"))
                out["price"] = out["price"] or price
                out["currency"] = out["currency"] or cur

    m = p.meta
    out["name"] = out["name"] or m.get("og:title") or m.get("twitter:title")
    out["image_url"] = out["image_url"] or m.get("og:image") or m.get("twitter:image")
    out["price"] = out["price"] or m.get("product:price:amount") or m.get("og:price:amount")
    out["currency"] = out["currency"] or m.get("product:price:currency") or m.get("og:price:currency")

    if out["image_url"]:
        out["image_url"] = urljoin(base_url, out["image_url"])
    if out["name"]:
        out["name"] = re.sub(r"\s+", " ", str(out["name"])).strip()
    return out


def scrape_product(url: str) -> dict:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=30)
    r.raise_for_status()
    return parse_product_html(r.text, r.url)


def format_price(price, currency, fallback="RM") -> str:
    """'1299' -> 'RM 1,299'; passes through text that already has a currency."""
    if price is None or str(price).strip() == "":
        return ""
    s = str(price).strip()
    if re.search(r"[A-Za-z$]", s):
        return s
    try:
        num = float(s.replace(",", ""))
    except ValueError:
        return s
    cur = {"MYR": "RM"}.get((currency or "").upper(), currency or fallback)
    txt = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    return f"{cur} {txt}"


def download_image(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    return r.content
