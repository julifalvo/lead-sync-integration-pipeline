"""Record the README demo GIF from the running dashboard.

    docker compose up -d                                   # stack must be running with data
    python -m src.generator.generate_leads --count 600 --spread-days 13
    uv pip install playwright && python -m playwright install chromium
    python scripts/record_demo.py

Requires ffmpeg on PATH. Output lands in docs/assets/dashboard.gif.
"""

import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
WORK = ROOT / "scripts" / ".recordings"
DASHBOARD = "http://localhost:8501"
GIF_WIDTH = 1200

# Playwright videos have no pointer; draw one so viewers can follow the interaction.
CURSOR_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;z-index:2147483647;width:18px;height:18px;margin:-9px 0 0 -9px;'
    + 'border-radius:50%;background:rgba(42,120,214,.35);border:2px solid #2a78d6;'
    + 'pointer-events:none;transition:transform .08s;left:-40px;top:-40px';
  document.body.appendChild(dot);
  document.addEventListener('mousemove', e => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
});
"""


def to_gif(source: str, output: Path, fps: int = 8) -> None:
    palette = (
        f"fps={fps},scale={GIF_WIDTH}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=max_colors=128:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", source, "-vf", palette, str(output)]
    subprocess.run(cmd, check=True)
    print(f"wrote {output.relative_to(ROOT)} ({output.stat().st_size / 1e6:.1f} MB)")


def record_dashboard() -> None:
    videos = WORK / "dashboard"
    shutil.rmtree(videos, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(videos),
            record_video_size={"width": 1440, "height": 900},
        )
        context.add_init_script(CURSOR_JS)
        page = context.new_page()
        page.goto(DASHBOARD, wait_until="networkidle")
        page.wait_for_selector("text=Lead Sync Integration Pipeline", timeout=60_000)
        page.wait_for_selector("text=Leads synced per day", timeout=30_000)
        page.wait_for_timeout(2800)  # let the charts finish their draw-in animation

        def glide(x: int, y: int, steps: int = 25, pause: int = 600) -> None:
            page.mouse.move(x, y, steps=steps)
            page.wait_for_timeout(pause)

        def scroll_page(delta_y: int) -> None:
            # page.mouse.wheel() scrolls/zooms whatever is under the cursor -- if that's a
            # Vega-Lite chart it zooms the chart instead of the page, and the page body itself
            # doesn't scroll in Streamlit -- the [data-testid="stMain"] section does.
            page.eval_on_selector('[data-testid="stMain"]', "(el, dy) => el.scrollBy(0, dy)", delta_y)

        # hover the top metrics, left to right
        for x in (220, 500, 780, 1060):
            glide(x, 230, steps=15, pause=450)

        # a single slow sweep across the "leads synced per day" bar chart
        glide(300, 500, steps=20, pause=300)
        glide(900, 500, steps=35, pause=1200)

        # scroll to "leads by source" and let its draw-in animation fully finish before touching it
        scroll_page(480)
        page.wait_for_timeout(2000)
        glide(600, 520, steps=25, pause=1200)

        # scroll to the recent events / errors tables and hold
        scroll_page(650)
        page.wait_for_timeout(2000)
        glide(400, 450, steps=20, pause=2500)

        video = page.video.path()
        context.close()
        browser.close()
    to_gif(video, ASSETS / "dashboard.gif")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    record_dashboard()


if __name__ == "__main__":
    main()
