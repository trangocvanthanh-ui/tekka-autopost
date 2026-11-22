"""Offline tests: schedule logic, idempotency, partial-failure retry (Meta API mocked)."""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import main as app  # noqa: E402
from meta import MetaError  # noqa: E402

CSV = """date,time,product_url,hook,name,price,image_url,platforms
2026-11-20,07:00,http://localhost:8765/sofa.html,,,,,
"""

from sheet import parse_csv_text  # noqa: E402

# --- parsing: short_url + approval gate -------------------------------------
old = parse_csv_text(CSV)
assert old[0].approved is True and old[0].short_url == "", "old sheets must keep working"
new = parse_csv_text("date,time,product_url,hook,name,price,image_url,platforms,short_url,approved\n"
                     "2026-11-20,07:00,http://a/1,,,,,,bit.ly/x,Y\n"
                     "2026-11-20,07:05,http://a/2,,,,,,,\n"
                     "2026-11-20,07:10,http://a/3,,,,,,,n\n"
                     "2026-11-20,07:15,,,,,,,,Y\n")
assert [r.approved for r in new] == [True, False, False], [r.approved for r in new]
assert new[0].short_url == "bit.ly/x" and len(new) == 3, "row without product_url is ignored"



def run(now, fb_fails=False):
    calls = {"ig": 0, "fb": 0}

    def ig(self, url):
        calls["ig"] += 1
        return "ig123"

    def fb(self, path):
        calls["fb"] += 1
        if fb_fails:
            raise MetaError("boom")
        return "fb456"

    with mock.patch.object(app.Meta, "ig_story", ig), mock.patch.object(app.Meta, "fb_story", fb), \
            mock.patch.object(app, "push_poster", lambda p, i: "https://x/y.jpg"):
        argv = ["main.py", "--sheet-file", str(tmp / "q.csv"), "--now", now, "--out-dir", str(tmp / "posters")]
        with mock.patch.object(sys, "argv", argv):
            try:
                app.main()
            except SystemExit as e:
                return calls, e.code
    return calls, 0


tmp = Path(tempfile.mkdtemp())
(tmp / "q.csv").write_text(CSV)
app.ROOT = tmp  # state file goes to temp
(tmp / "brand").mkdir()
shutil.copy(ROOT / "brand" / "config.json", tmp / "brand" / "config.json")
os.environ.update(META_PAGE_TOKEN="t", IG_USER_ID="1", FB_PAGE_ID="2", NO_PROXY="localhost")

c, code = run("2026-11-20 06:59");            assert c == {"ig": 0, "fb": 0}, "must not post early"
c, code = run("2026-11-20 07:05", fb_fails=True); assert c == {"ig": 1, "fb": 1} and code == 1, (c, code)
c, code = run("2026-11-20 07:20");            assert c == {"ig": 0, "fb": 1} and code == 0, ("IG must not repost", c, code)
c, code = run("2026-11-20 07:35");            assert c == {"ig": 0, "fb": 0}, "no repost after done"
print("ALL OK")
