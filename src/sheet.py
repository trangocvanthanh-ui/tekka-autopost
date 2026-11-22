"""Read the posting queue from a Google Sheet published as CSV."""
import csv
import hashlib
import io
from dataclasses import dataclass, field

import requests

PLATFORMS_ALL = ("IG", "FB")


@dataclass
class Row:
    date: str
    time: str
    product_url: str
    hook: str = ""
    name: str = ""
    price: str = ""
    image_url: str = ""
    platforms: tuple = PLATFORMS_ALL
    short_url: str = ""
    approved: bool = True  # always True when the sheet has no 'approved' column
    line: int = 0

    @property
    def id(self) -> str:
        raw = f"{self.date}|{self.time}|{self.product_url}".encode()
        return hashlib.sha1(raw).hexdigest()[:12]


def _norm(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_")


def parse_platforms(value: str) -> tuple:
    v = (value or "").upper().replace(";", ",").replace("+", ",").replace("/", ",")
    found = tuple(p for p in PLATFORMS_ALL if p in [x.strip() for x in v.split(",")] or
                  (p == "FB" and "FACEBOOK" in v) or (p == "IG" and "INSTAGRAM" in v))
    return found or PLATFORMS_ALL


def is_approved(value: str) -> bool:
    return (value or "").strip().upper() in ("Y", "YES", "TRUE", "1", "OK", "X")


def parse_csv_text(text: str) -> list:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    # Approval gate: only active if the sheet has an 'approved' column at all.
    has_approved_col = "approved" in [_norm(h) for h in (reader.fieldnames or [])]
    for i, raw in enumerate(reader, start=2):  # line 1 is the header
        d = {_norm(k): (v or "").strip() for k, v in raw.items() if k}
        if not d.get("product_url") or not d.get("date") or not d.get("time"):
            continue  # blank / incomplete rows are ignored
        rows.append(Row(
            date=d["date"], time=d["time"], product_url=d["product_url"],
            hook=d.get("hook", ""), name=d.get("name", ""), price=d.get("price", ""),
            image_url=d.get("image_url", ""), platforms=parse_platforms(d.get("platforms", "")),
            short_url=d.get("short_url", ""),
            approved=is_approved(d.get("approved", "")) if has_approved_col else True,
            line=i,
        ))
    return rows


def fetch_rows(csv_url: str) -> list:
    r = requests.get(csv_url, timeout=30)
    r.raise_for_status()
    return parse_csv_text(r.content.decode("utf-8-sig"))
