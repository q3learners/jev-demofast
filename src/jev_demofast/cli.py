"""jev-demofast command line.

  jev-demofast chrome [--open URL]                     start an isolated Chrome (log in once; it remembers)
  jev-demofast demo "<prompt>" --url URL [--index F]   prompt → MP4 (+ --gif, --voice NAME for narration)
  jev-demofast index <repo> --out app-index.json       map a Next.js app from source
  jev-demofast run / narrate / render                  the stages of `demo`, one at a time
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import load, quiet_browser_harness

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]


MY_BROWSER_WARNING = """
--use-my-browser drives YOUR everyday Chrome, as you:
  • it acts under your real logins (often production, not staging); guards stay on, but mistakes are real;
  • it works in a new tab and never touches your other tabs; it stays on {host};
  • Chrome must have remote debugging switched on (chrome://inspect/#remote-debugging), and asks you to allow it.
Prefer `jev-demofast chrome --open <url>`: log in once in the tool's own profile, and your browser stays untouched.
"""


def choose_browser(a, settings):
    """Point browser-harness at the isolated Chrome (default) or, opt-in, the user's own running Chrome."""
    from urllib.parse import urlparse
    if getattr(a, "use_my_browser", False):
        if getattr(a, "fresh", False):
            raise SystemExit("--fresh would clear this site's cookies in your own browser (logging you out). "
                             "It is refused with --use-my-browser.")
        print(MY_BROWSER_WARNING.format(host=urlparse(a.url).hostname), file=sys.stderr)
        if not getattr(a, "yes", False):
            if not sys.stdin.isatty():
                raise SystemExit("--use-my-browser needs confirmation: run it interactively, or add --yes.")
            if input("Type 'yes' to continue in your own browser: ").strip().lower() != "yes":
                raise SystemExit("Stopped. Nothing was opened.")
        for var in ("BU_CDP_URL", "BU_CDP_WS"):  # no address: browser-harness discovers the running Chrome
            os.environ.pop(var, None)
        os.environ["BU_NAME"] = "jdf-my-browser"  # a separate harness connection, never reused for the isolated one
    else:
        os.environ.setdefault("BU_CDP_URL", settings.cdp_url)
        os.environ.setdefault("BU_NAME", "jdf-isolated")


def _cf(a=None, require=True):
    from .cloudflare import Cloudflare
    settings = load(require_cloudflare=require)
    choose_browser(a or argparse.Namespace(), settings)
    quiet_browser_harness()
    return Cloudflare(settings)


def cmd_chrome(a):
    binary = next((c for c in CHROME_CANDIDATES if Path(c).exists() or shutil.which(c)), None)
    if not binary:
        raise SystemExit("Chrome not found; start it yourself with --remote-debugging-port=9333 and a separate profile")
    profile = Path(a.profile).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([shutil.which(binary) or binary, f"--user-data-dir={profile}", f"--remote-debugging-port={a.port}",
                      "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check",
                      "--window-size=1440,900", a.open or "about:blank"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    print(f"Isolated Chrome started (profile {profile}, debugging on 127.0.0.1:{a.port}). "
          f"Your normal browser and its logins are untouched.")
    if a.open:
        print(f"Log in to {a.open} in that window now (SSO and 2-factor work: you do them). The profile remembers it:\n"
              f"later demos start logged in. Don't pass --fresh (it clears this site's cookies).")


def cmd_index(a):
    from . import index
    idx = index.build(a.repo, a.framework)
    index.save(idx, a.out)
    print(f"{len(idx)} routes, {sum(len(r['links']) for r in idx.values())} links → {a.out}")


def cmd_run(a, cf=None):
    cf = cf or _cf(a)
    if a.index:
        from .drive import jev_drive
        from .index import load as load_index
        return jev_drive.run(cf, a.url, a.goal, load_index(a.index), out=a.work, fresh=a.fresh, blur_typed=not a.no_blur)
    from .drive import navigator
    return navigator.run(cf, a.url, a.goal, out=a.work, picker=a.picker, fresh=a.fresh,
                         page_maps=bool(getattr(a, "voice", None)) or getattr(a, "page_maps", False),
                         blur_typed=not a.no_blur)


def cmd_narrate(a, cf=None):
    """Script → voice → camera-follow → narrated MP4, from a run recorded with page maps."""
    cf = cf or _cf(a)
    from .narrate import focus, script, voice
    from .render.assemble import assemble
    path = script.write(cf, a.work, product=a.product)
    clips = voice.generate(cf, path, os.path.join(a.work, "voice"), speaker=a.voice)
    focused = focus.follow(cf, a.work, path, clips, os.path.join(a.work, "focused"))
    return assemble(focused, a.out, clips_dir=clips, gif=a.gif)


def cmd_render(a):
    from .render.assemble import assemble
    return assemble(a.work, a.out, gif=a.gif)


def cmd_demo(a):
    cf = _cf(a)
    a.work = a.work or str(Path(a.out).with_suffix("")) + ".run"
    a.goal = a.prompt
    result = cmd_run(a, cf)
    if a.voice and not a.index:
        cmd_narrate(a, cf)
    else:
        if a.voice:
            print("note: narration needs the navigator's page maps; rendering without voice for --index runs")
        cmd_render(a)
    print(f"verified: {result.get('verified')} | {result.get('seconds')} s | Jev {result.get('jev_calls')} calls")


def main(argv=None):
    p = argparse.ArgumentParser(prog="jev-demofast", description="One sentence in, a product demo video out.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("chrome", help="start an isolated Chrome for the tool to drive")
    c.add_argument("--port", type=int, default=9333)
    c.add_argument("--profile", default="~/.cache/jev-demofast/chrome-profile")
    c.add_argument("--open", metavar="URL", help="open this page so you can log in once; the profile remembers it")
    c.set_defaults(fn=cmd_chrome)

    i = sub.add_parser("index", help="build an app index from source")
    i.add_argument("repo")
    i.add_argument("--framework", default="nextjs")
    i.add_argument("--out", default="app-index.json")
    i.set_defaults(fn=cmd_index)

    def run_args(sp):
        sp.add_argument("--url", required=True, help="where the demo starts (use staging)")
        sp.add_argument("--index", help="app index JSON: Jev drives from it, no LLM plan")
        sp.add_argument("--picker", default="jev", choices=["jev", "hybrid", "keyword"],
                        help="without an index: who picks elements (default: jev)")
        sp.add_argument("--fresh", action="store_true", help="clear the site's cookies first (start logged out)")
        sp.add_argument("--no-blur", action="store_true", help="show typed values in the video")
        sp.add_argument("--use-my-browser", action="store_true",
                        help="drive your own running Chrome with its logins (opt-in; asks for confirmation)")
        sp.add_argument("--yes", action="store_true", help="skip the --use-my-browser confirmation (scripts)")

    d = sub.add_parser("demo", help="prompt → demo video")
    d.add_argument("prompt", help='e.g. "Reset my password for {{EMAIL}}"; secrets as {{NAME}} + env DEMO_NAME')
    run_args(d)
    d.add_argument("--out", default="demo.mp4")
    d.add_argument("--work", help="folder for frames (default: <out>.run)")
    d.add_argument("--gif", action="store_true")
    d.add_argument("--voice", help="narrate with this Aura-2 voice, e.g. apollo")
    d.add_argument("--product", default="", help="one line about the product, for narration")
    d.set_defaults(fn=cmd_demo)

    r = sub.add_parser("run", help="drive and record only")
    r.add_argument("--goal", required=True)
    run_args(r)
    r.add_argument("--work", required=True)
    r.add_argument("--page-maps", action="store_true", help="record page maps so `narrate` can follow the camera")
    r.set_defaults(fn=cmd_run)

    n = sub.add_parser("narrate", help="script + voice + camera-follow + render, from a recorded run")
    n.add_argument("work")
    n.add_argument("--out", required=True)
    n.add_argument("--voice", default="apollo")
    n.add_argument("--product", default="")
    n.add_argument("--gif", action="store_true")
    n.set_defaults(fn=cmd_narrate)

    v = sub.add_parser("render", help="frames → MP4 (+ GIF)")
    v.add_argument("work")
    v.add_argument("--out", required=True)
    v.add_argument("--gif", action="store_true")
    v.set_defaults(fn=cmd_render)

    a = p.parse_args(argv)
    import httpx
    from .cloudflare import ModelError
    try:
        a.fn(a)
    except (httpx.HTTPError, ModelError) as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
