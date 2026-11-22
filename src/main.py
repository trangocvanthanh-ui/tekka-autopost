"""Tekkashop auto-poster: Google Sheet queue -> Story poster -> Instagram + Facebook Stories."""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meta import Meta, MetaError  # noqa: E402
from poster import build_poster, save_jpeg  # noqa: E402
from scrape import download_image, format_price, scrape_product  # noqa: E402
from sheet import fetch_rows, parse_csv_text  # noqa: E402
from state import State  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y")


def parse_when(date: str, tm: str, tz: ZoneInfo) -> datetime:
    t = None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            t = datetime.strptime(tm.strip().upper(), fmt).time()
            break
        except ValueError:
            pass
    d = None
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(date.strip(), fmt).date()
            break
        except ValueError:
            pass
    if t is None or d is None:
        raise ValueError(f"cannot read date/time: '{date}' '{tm}' (use YYYY-MM-DD and HH:MM)")
    return datetime.combine(d, t, tzinfo=tz)


def log(msg: str, summary: list):
    print(msg, flush=True)
    summary.append(msg)


def push_poster(path: Path, row_id: str) -> str:
    """Commit the poster to the (public) repo so Instagram can download it; return the raw URL."""
    repo, branch = os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_REF_NAME", "main")
    rel = path.relative_to(ROOT).as_posix()
    run = lambda *a: subprocess.run(a, cwd=ROOT, check=True, capture_output=True, text=True)  # noqa: E731
    run("git", "add", rel)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        run("git", "commit", "-m", f"poster {row_id}")
        run("git", "pull", "--rebase", "origin", branch)
        run("git", "push", "origin", f"HEAD:{branch}")
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{rel}"
    for _ in range(18):
        if requests.head(url, timeout=15).status_code == 200:
            return url
        time.sleep(5)
    raise RuntimeError(f"poster not reachable at {url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="make posters but post nothing, save no state")
    ap.add_argument("--sheet-file", help="read a local CSV instead of SHEET_CSV_URL")
    ap.add_argument("--now", help="pretend the time is 'YYYY-MM-DD HH:MM' (Malaysia time), for testing")
    ap.add_argument("--out-dir", default=str(ROOT / "posters"))
    args = ap.parse_args()

    cfg = json.loads((ROOT / "brand" / "config.json").read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.strptime(args.now, "%Y-%m-%d %H:%M").replace(tzinfo=tz) if args.now \
        else datetime.now(tz)
    tolerance = timedelta(hours=cfg["late_tolerance_hours"])
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = [f"Run at {now:%Y-%m-%d %H:%M} ({cfg['timezone']})" + ("  [DRY RUN]" if args.dry_run else "")]

    if args.sheet_file:
        rows = parse_csv_text(Path(args.sheet_file).read_text(encoding="utf-8-sig"))
    else:
        rows = fetch_rows(os.environ["SHEET_CSV_URL"])
    state = State(ROOT / "state" / "state.json")

    client = None
    if not args.dry_run:
        client = Meta(os.environ["META_PAGE_TOKEN"], os.environ["IG_USER_ID"],
                      os.environ["FB_PAGE_ID"], cfg["graph_version"])

    failures = 0
    waiting = [r for r in rows if not r.approved and not state.data.get(r.id, {}).get("status")]
    if waiting:
        log(f"{len(waiting)} row(s) waiting for approval (approved column is not Y): "
            f"lines {', '.join(str(r.line) for r in waiting)}", summary)
    for row in rows:
        tag = f"row {row.line} [{row.id}]"
        if not row.approved:
            continue
        try:
            when = parse_when(row.date, row.time, tz)
        except ValueError as e:
            log(f"{tag}: SKIP - {e}", summary)
            failures += 1
            continue
        st = state.get(row.id)
        pending = [p for p in row.platforms if not st.get(f"{p}_id")]
        if not pending or st.get("status") in ("missed", "failed"):
            continue
        if when > now:
            continue
        if now - when > tolerance:
            st["status"] = "missed"
            log(f"{tag}: MISSED - was due {when:%Y-%m-%d %H:%M}, more than "
                f"{cfg['late_tolerance_hours']}h ago", summary)
            continue
        if st.get("attempts", 0) >= cfg["max_attempts"]:
            st["status"] = "failed"
            log(f"{tag}: FAILED after {cfg['max_attempts']} attempts: {st.get('error')}", summary)
            failures += 1
            continue

        poster_path = out_dir / f"{row.id}.jpg"
        try:
            if not poster_path.exists():
                info = {"name": row.name, "price": row.price, "image_url": row.image_url, "currency": None}
                if not (row.name and row.image_url and row.price):
                    try:
                        scraped = scrape_product(row.product_url)
                        for k in ("name", "image_url", "currency"):
                            info[k] = info[k] or scraped[k]
                        info["price"] = info["price"] or scraped["price"]
                    except Exception as e:  # noqa: BLE001
                        if not info["image_url"]:
                            raise RuntimeError(f"cannot read product page: {e}")
                if not info["image_url"]:
                    raise RuntimeError("no product image found; add an image_url in the sheet")
                hook = row.hook or cfg["default_hooks"][int(row.id, 16) % len(cfg["default_hooks"])]
                price_txt = format_price(info["price"], info["currency"], cfg["currency_fallback"])
                img = build_poster(download_image(info["image_url"]), info["name"] or "", price_txt, hook, cfg,
                                   short_url=row.short_url)
                save_jpeg(img, poster_path)

            if args.dry_run:
                log(f"{tag}: DRY RUN - poster saved {poster_path.name}; would post to {', '.join(pending)}", summary)
                continue

            st["attempts"] = st.get("attempts", 0) + 1
            raw_url = push_poster(poster_path, row.id) if "IG" in pending else None
            for p in pending:
                try:
                    st[f"{p}_id"] = client.ig_story(raw_url) if p == "IG" else client.fb_story(str(poster_path))
                    log(f"{tag}: {p} Story posted ({st[f'{p}_id']})", summary)
                except MetaError as e:
                    st["error"] = f"{p}: {e}"
                    failures += 1
                    log(f"{tag}: {p} FAILED - {e}", summary)
            if all(st.get(f"{p}_id") for p in row.platforms):
                st["status"] = "done"
                st["posted_at"] = now.isoformat()
                st.pop("error", None)
        except Exception as e:  # noqa: BLE001
            st["error"] = str(e)
            failures += 1
            log(f"{tag}: ERROR - {e}", summary)

    if len(summary) == 1:
        summary.append("Nothing due.")
    if not args.dry_run:
        state.save()
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Tekkashop auto-poster\n" + "\n".join(f"- {s}" for s in summary) + "\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
