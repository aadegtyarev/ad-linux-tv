"""Opt-in, disposable Firefox geometry test; no user profile or media is read.

Run with AD_LINUX_TV_BROWSER_TEST=1 pytest -q tests/test_launcher_browser_layout.py.
Firefox and geckodriver must be installed. This test starts only local servers.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/ad_linux_tv/static"
pytestmark = pytest.mark.skipif(
    os.environ.get("AD_LINUX_TV_BROWSER_TEST") != "1",
    reason="set AD_LINUX_TV_BROWSER_TEST=1 to run the isolated Firefox geometry test",
)


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/":
            html = (STATIC / "index.html").read_text().split('<script src="/layout.js">')[0]
            html = (
                html.replace(
                    '<p id="bridge-status"></p>',
                    '<p id="bridge-status">Расширение Firefox подключено.</p>',
                )
                .replace(
                    '<p id="command-status"></p>',
                    '<p id="command-status">Проверьте соединение и повторите попытку позже.</p>',
                )
                .replace(
                    '<img id="qr" alt="QR-код пульта" hidden>',
                    '<img id="qr" alt="QR-код пульта" src="/qr.svg">',
                )
            )
            body = (
                html + '<script src="/layout.js"></script>'
                '<script src="/launcher_ui.js"></script>'
                '<script src="/fixture.js"></script></html>'
            ).encode()
            kind = "text/html; charset=utf-8"
        elif self.path in (
            "/style.css",
            "/bluetooth_controls.css",
            "/layout.js",
            "/launcher_ui.js",
        ):
            body = (STATIC / self.path[1:]).read_bytes()
            kind = "text/css" if self.path.endswith(".css") else "text/javascript"
        elif self.path == "/fixture.js":
            body = b"window.fixtureUI=createLauncherUI(()=>{},()=>{});"
            kind = "text/javascript"
        elif self.path == "/qr.svg":
            body = (
                b'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220">'
                b'<rect width="220" height="220" fill="white"/>'
                b'<rect x="15" y="15" width="60" height="60" fill="black"/>'
                b'<rect x="145" y="15" width="60" height="60" fill="black"/>'
                b'<rect x="15" y="145" width="60" height="60" fill="black"/></svg>'
            )
            kind = "image/svg+xml"
        else:
            body = b"<!doctype html><title>Synthetic service</title>"
            kind = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port, method, path, value=None):
    data = None if value is None else json.dumps(value).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)["value"]


def execute(port, session, script, *args):
    return request(
        port, "POST", f"/session/{session}/execute/sync", {"script": script, "args": args}
    )


def wait_until(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, KeyError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise AssertionError("disposable Firefox did not reach the expected state")


def test_launcher_fit_and_scroll_fallback():
    assert shutil.which("firefox") and shutil.which("geckodriver")
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = free_port()
    env = dict(os.environ, MOZ_HEADLESS_WIDTH="1360", MOZ_HEADLESS_HEIGHT="1000")
    # Snap Firefox requires profiles below its own home; other installs use /tmp.
    snap_home = Path.home() / "snap/firefox/common"
    profile_parent = snap_home if snap_home.is_dir() else None
    session = None
    try:
        with tempfile.TemporaryDirectory(
            prefix="ad-tv-layout-", dir=profile_parent
        ) as profile_root:
            driver = subprocess.Popen(
                [
                    "geckodriver",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--allow-system-access",
                    "--profile-root",
                    profile_root,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                wait_until(lambda: request(port, "GET", "/status")["ready"])
                home = f"http://127.0.0.1:{server.server_port}/"
                session = request(
                    port,
                    "POST",
                    "/session",
                    {
                        "capabilities": {
                            "alwaysMatch": {
                                "browserName": "firefox",
                                "moz:firefoxOptions": {
                                    "args": ["-headless"],
                                    "prefs": {
                                        "browser.startup.homepage": home,
                                        "browser.zoom.siteSpecific": False,
                                    },
                                },
                            }
                        }
                    },
                )["sessionId"]
                rect = request(
                    port,
                    "POST",
                    f"/session/{session}/window/rect",
                    {"x": 0, "y": 0, "width": 1360, "height": 850},
                )
                viewport = execute(port, session, "return {width:innerWidth,height:innerHeight};")
                request(
                    port,
                    "POST",
                    f"/session/{session}/window/rect",
                    {
                        "x": 0,
                        "y": 0,
                        "width": rect["width"] + 1360 - viewport["width"],
                        "height": rect["height"] + 768 - viewport["height"],
                    },
                )
                request(port, "POST", f"/session/{session}/url", {"url": home + "watch"})
                addon = Path(profile_root) / "zoom.xpi"
                with zipfile.ZipFile(addon, "w") as archive:
                    archive.writestr(
                        "manifest.json",
                        json.dumps(
                            {
                                "manifest_version": 3,
                                "name": "Disposable zoom fixture",
                                "version": "1.0",
                                "browser_specific_settings": {
                                    "gecko": {"id": "layout-probe@example.invalid"}
                                },
                                "permissions": ["tabs"],
                                "background": {"scripts": ["zoom.js"]},
                            }
                        ),
                    )
                    archive.writestr(
                        "zoom.js",
                        "browser.tabs.query({active:true,currentWindow:true})"
                        ".then(([tab])=>browser.tabs.setZoom(tab.id,1.25));",
                    )
                request(
                    port,
                    "POST",
                    f"/session/{session}/moz/addon/install",
                    {"path": str(addon), "temporary": True},
                )
                wait_until(lambda: execute(port, session, "return innerWidth === 1088;"))
                request(port, "POST", f"/session/{session}/moz/context", {"context": "chrome"})
                execute(port, session, "BrowserCommands.home();")
                request(port, "POST", f"/session/{session}/moz/context", {"context": "content"})
                wait_until(lambda: execute(port, session, "return !!window.fixtureUI;"))
                for count in range(1, 13):
                    result = execute(
                        port,
                        session,
                        """
                      const n=arguments[0];
                      fixtureUI.update(Array.from({length:n},(_,i)=>
                        ({id:`s${i}`,name:'ШШШШШШШШШ ШШШ'})),12);
                      const nodes=[...document.querySelectorAll('#tiles button')];
                      const rects=nodes.map(x=>x.getBoundingClientRect());
                      const qr=document.querySelector('#remote-setup').getBoundingClientRect();
                      const image=document.querySelector('#qr');
                      const ir=image.getBoundingClientRect();
                      const status=document.querySelector('#bridge-status');
                      const sr=status.getBoundingClientRect();
                      nodes[0].focus();
                      document.dispatchEvent(new KeyboardEvent('keydown',
                        {key:'ArrowDown',bubbles:true}));
                      const down=Number(document.activeElement.dataset.serviceIndex);
                      return {width:innerWidth,height:innerHeight,count:nodes.length,down,
                        allVisible:rects.every(r=>r.top>=0&&r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight),
                        labelOverflow:nodes.some(x=>x.scrollWidth>x.clientWidth||x.scrollHeight>x.clientHeight),
                        scrollHeight:document.documentElement.scrollHeight,qrBottom:qr.bottom,
                        qrLoaded:image.complete&&image.naturalWidth>0&&ir.width>=160&&ir.height>=160,
                        statusVisible:getComputedStyle(status).display!=='none'&&sr.width>0&&
                          sr.height>0&&sr.top>=0&&sr.bottom<=innerHeight,
                        header:getComputedStyle(document.querySelector('.topbar')).flexDirection};
                    """,
                        count,
                    )
                    assert (result["width"], result["height"]) == (1088, 614)
                    assert result["count"] == count and result["allVisible"]
                    assert (
                        not result["labelOverflow"] and result["scrollHeight"] <= result["height"]
                    )
                    assert result["qrBottom"] <= result["height"] and result["header"] == "row"
                    assert result["qrLoaded"] and result["statusVisible"]
                    assert result["down"] == (3 if count > 3 else 0)
                pages = execute(
                    port,
                    session,
                    """
                  fixtureUI.update(Array.from({length:13},(_,i)=>({id:`s${i}`,name:'Сервис'})),12);
                  const tiles=[...document.querySelectorAll('#tiles button')];
                  const nav=document.querySelector('.pagination').getBoundingClientRect();
                  const bottom=Math.max(...tiles.map(x=>x.getBoundingClientRect().bottom));
                  const separated=bottom<=nav.top;
                  const nextButton=document.querySelector('#next');
                  nextButton.focus();nextButton.scrollIntoView({block:'end'});
                  const nextRect=nextButton.getBoundingClientRect();
                  // innerHeight is integer-rounded; Firefox can expose a fractional viewport.
                  const reachable=nextRect.top>=0&&nextRect.bottom<=innerHeight+1;
                  const debug={top:nextRect.top,bottom:nextRect.bottom,height:innerHeight,
                    scroll:scrollY,documentHeight:document.documentElement.scrollHeight};
                  nextButton.click();
                  const next=[...document.querySelectorAll('#tiles button')]
                    .map(x=>x.dataset.serviceIndex);
                  document.querySelector('#prev').click();
                  const returned=document.querySelectorAll('#tiles button').length;
                  return {separated,reachable,next,returned,debug};
                """,
                )
                assert pages["separated"] and pages["reachable"], pages["debug"]
                assert pages["next"] == ["12"] and pages["returned"] == 12
                fallback = execute(
                    port,
                    session,
                    """
                  fixtureUI.update(Array.from({length:12},(_,i)=>({id:`s${i}`,name:'Ш'.repeat(80)})),12);
                  const nodes=[...document.querySelectorAll('#tiles button')];
                  const last=nodes.at(-1);last.focus();
                  scrollTo(0,document.documentElement.scrollHeight);
                  const r=last.getBoundingClientRect();
                  const ancestorClips=nodes.some(node=>{
                    const box=node.getBoundingClientRect();
                    for(let p=node.parentElement;p&&p!==document.documentElement;p=p.parentElement){
                      const s=getComputedStyle(p), a=p.getBoundingClientRect();
                      if(['hidden','clip'].includes(s.overflowY)&&
                        (box.top<a.top||box.bottom>a.bottom)) return true;
                    }
                    return false;
                  });
                  return {scroll:document.documentElement.scrollHeight>innerHeight,
                    clipped:nodes.some(x=>x.scrollWidth>x.clientWidth||x.scrollHeight>x.clientHeight),
                    horizontal:document.documentElement.scrollWidth>innerWidth,
                    reachable:r.top>=0&&r.bottom+7<=innerHeight&&!ancestorClips};
                """,
                )
                assert fallback == {
                    "scroll": True,
                    "clipped": False,
                    "horizontal": False,
                    "reachable": True,
                }
                system = execute(
                    port,
                    session,
                    """
                    document.querySelector('#home').hidden=true;
                    document.querySelector('#settings').hidden=false;
                    const result={home:getComputedStyle(document.querySelector('#home')).display,
                      settings:getComputedStyle(document.querySelector('#settings')).display};
                    document.querySelector('#settings').hidden=true;
                    document.querySelector('#home').hidden=false;
                    return result;
                    """,
                )
                assert system["home"] == "none" and system["settings"] != "none"
                for zoom in (*[percent / 100 for percent in range(100, 126)], 2.0):
                    request(port, "POST", f"/session/{session}/moz/context", {"context": "chrome"})
                    execute(
                        port,
                        session,
                        "ZoomManager.setZoomForBrowser(gBrowser.selectedBrowser, arguments[0]);",
                        zoom,
                    )
                    request(port, "POST", f"/session/{session}/moz/context", {"context": "content"})
                    for count in range(1, 13):
                        result = execute(
                            port,
                            session,
                            """
                          fixtureUI.update(Array.from({length:arguments[0]},(_,i)=>
                            ({id:`s${i}`,name:'ШШШШШШШШШ ШШШ'})),12);
                          scrollTo(0,0);
                          const nodes=[...document.querySelectorAll('#tiles button')];
                          const rects=nodes.map(x=>x.getBoundingClientRect());
                          return {visible:rects.every(r=>r.top>=0&&r.left>=0&&
                              r.right<=innerWidth&&r.bottom<=innerHeight),
                            clipped:nodes.some(x=>x.scrollWidth>x.clientWidth||x.scrollHeight>x.clientHeight),
                            scroll:document.documentElement.scrollHeight>innerHeight};
                        """,
                            count,
                        )
                        assert not result["clipped"]
                        if zoom <= 1.25:
                            assert result["visible"] and not result["scroll"]
                        elif count == 12:
                            assert result["scroll"]
                            reachable = execute(
                                port,
                                session,
                                """
                                const tile=document.querySelector('#tiles button:last-child');
                                tile.focus();tile.scrollIntoView({block:'end'});
                                const r=tile.getBoundingClientRect();
                                return r.top>=0&&r.bottom<=innerHeight&&
                                  document.documentElement.scrollWidth<=innerWidth;
                                """,
                            )
                            assert reachable
                request(port, "POST", f"/session/{session}/moz/context", {"context": "chrome"})
                execute(
                    port, session, "ZoomManager.setZoomForBrowser(gBrowser.selectedBrowser, 1);"
                )
                request(port, "POST", f"/session/{session}/moz/context", {"context": "content"})
                for width in (600, 700, 701, 900, 901, 1100, 1101):
                    for _ in range(4):
                        rect = request(port, "GET", f"/session/{session}/window/rect")
                        viewport = execute(port, session, "return {w:innerWidth,h:innerHeight};")
                        if viewport == {"w": width, "h": 600}:
                            break
                        request(
                            port,
                            "POST",
                            f"/session/{session}/window/rect",
                            {
                                "x": 0,
                                "y": 0,
                                "width": rect["width"] + width - viewport["w"],
                                "height": rect["height"] + 600 - viewport["h"],
                            },
                        )
                    boundary = execute(
                        port,
                        session,
                        """
                      fixtureUI.update(Array.from({length:12},(_,i)=>
                        ({id:`s${i}`,name:'ШШШШШШШШШ ШШШ'})),12);
                      const tiles=[...document.querySelectorAll('#tiles button')];
                      const title=document.querySelector('h1').getBoundingClientRect();
                      const button=document.querySelector('#system-button').getBoundingClientRect();
                      const overlap=title.left<button.right&&button.left<title.right&&
                        title.top<button.bottom&&button.top<title.bottom;
                      const last=tiles.at(-1);last.focus();last.scrollIntoView({block:'end'});
                      const r=last.getBoundingClientRect();
                      return {width:innerWidth,height:innerHeight,overlap,
                        clipped:tiles.some(x=>x.scrollWidth>x.clientWidth||x.scrollHeight>x.clientHeight),
                        horizontal:document.documentElement.scrollWidth>innerWidth,
                        reachable:r.top>=0&&r.bottom<=innerHeight};
                    """,
                    )
                    assert boundary == {
                        "width": width,
                        "height": 600,
                        "overlap": False,
                        "clipped": False,
                        "horizontal": False,
                        "reachable": True,
                    }
            finally:
                if session:
                    try:
                        request(port, "DELETE", f"/session/{session}")
                    except OSError:
                        pass
                driver.terminate()
                try:
                    driver.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    driver.kill()
                    driver.wait(timeout=5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
