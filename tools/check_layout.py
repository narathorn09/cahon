"""Check the results list in WebKit, the engine of the Mac app's window (used by CI on macOS).

    python tools/check_layout.py "dist/CAHON.app/Contents/MacOS/CAHON"            # WebKit
    python tools/check_layout.py "dist/CAHON.app/Contents/MacOS/CAHON" chromium   # same check, Chromium

Starts the built app in browser mode with 60 files, so the list is taller than its scroll
area, opens it in WebKit and measures the rows: each must be its real height and none may
overlap the next. (Rows once shrank to slivers in WebKit while Chromium was fine.)
Needs: pip install playwright && python -m playwright install webkit
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


def get(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return json.loads(r.read())


def main() -> int:
    exe = Path(sys.argv[1]).resolve()
    engine = sys.argv[2] if len(sys.argv) > 2 else "webkit"
    tmp = Path(tempfile.mkdtemp(prefix="cahon-layout-"))
    home, data = tmp / "home", tmp / "data"
    docs = home / "Documents"
    docs.mkdir(parents=True)
    for i in range(60):
        (docs / f"รายงานประจำเดือน-{i:02d}.txt").write_text(f"รายงาน ฉบับที่ {i} ค่าใช้จ่ายสำนักงาน", encoding="utf-8")
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "CAHON_DATA_DIR": str(data), "CAHON_NO_WINDOW": "1"}
    proc = subprocess.Popen([str(exe)], env=env)
    ok = False
    try:
        port = None
        for _ in range(120):
            try:
                port = json.loads((data / "running.json").read_text())["port"]
                get(port, "/api/status")
                break
            except (OSError, ValueError, KeyError):
                time.sleep(1)
        assert port, "the app did not start"
        for _ in range(120):
            if get(port, "/api/status")["counts"]["file"] >= 60:
                break
            time.sleep(1)
        with sync_playwright() as p:
            browser = getattr(p, engine).launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.add_init_script("localStorage.setItem('cahon-tour-done', '1')")
            page.goto(f"http://127.0.0.1:{port}/")
            page.wait_for_selector("#results li.row", timeout=20000)
            page.wait_for_timeout(1200)
            info = page.evaluate("""() => {
                const ul = document.querySelector('#results');
                const rows = [...ul.querySelectorAll('li.row')].slice(0, 12).map(li => {
                    const r = li.getBoundingClientRect(), t = li.querySelector('.title');
                    return { top: r.top, bottom: r.bottom, h: r.height, titleH: t ? t.getBoundingClientRect().height : 0 };
                });
                return { rows, scroll: ul.scrollHeight, client: ul.clientHeight, n: ul.querySelectorAll('li.row').length };
            }""")
            page.screenshot(path=str(Path(os.environ.get("LAYOUT_SHOT", tmp / "layout.png"))))
            browser.close()
        rows = info["rows"]
        print(f"{engine}: {info['n']} rows, list {info['scroll']} px in a {info['client']} px area, "
              f"row heights {[round(r['h']) for r in rows]}")
        assert info["n"] >= 12, "too few rows to check"
        assert info["scroll"] > info["client"], "the list does not overflow its area, so the check proves nothing"
        short = [round(r["h"]) for r in rows if r["h"] < max(40, r["titleH"] * 2)]
        assert not short, f"rows squashed to {short} px"
        overlap = [i for i in range(len(rows) - 1) if rows[i + 1]["top"] < rows[i]["bottom"] - 1]
        assert not overlap, f"rows overlap after {overlap}"
        ok = True
    except AssertionError as exc:
        print("FAILED:", exc)
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("LAYOUT CHECK", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
