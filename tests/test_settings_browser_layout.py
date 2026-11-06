"""Disposable Firefox geometry checks; no real profiles, devices or media.

Run with AD_LINUX_TV_BROWSER_TEST=1 pytest -q tests/test_settings_browser_layout.py.
"""

import base64
import os
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_launcher_browser_layout import execute, free_port, request, wait_until

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/ad_linux_tv/static"
pytestmark = pytest.mark.skipif(
    os.environ.get("AD_LINUX_TV_BROWSER_TEST") != "1",
    reason="set AD_LINUX_TV_BROWSER_TEST=1 for disposable Firefox geometry checks",
)

PHONE_FIXTURE = """
<script src="/bluetooth_controls.js"></script><script>
window.fixtureBtCalls=[];
window.fixtureBtState={available:true, reason:'', revision:7,
  adapter:{id:'adapter',powered:true,discovering:false},
  devices:[{id:'device',name:'Длинное название синтетического пульта для проверки переноса',
    paired:false,connected:false,selected:true,input_available:true}],
  remote:null,operation:null};
window.fixtureBt = new BluetoothControls(document.querySelector('#phone-bluetooth-controls'),
  async(method,path,body)=>{
    window.fixtureBtCalls.push(body?.op || method);
    let extra={};
    if(body?.op==='acquire') extra.lease='a'.repeat(32);
    if(body?.op==='pair') {
      fixtureBtState.operation={id:'operation',kind:'pair',phase:'waiting',device_id:'device',
        remaining_ms:20000,error:''};
      extra.challenge={id:'challenge',kind:'pin',remaining_ms:10000};
    }
    if(body?.op==='forget_prepare') {
      fixtureBtState.operation={id:'operation2',kind:'forget',phase:'confirm',device_id:'device',
        remaining_ms:20000,error:''};
      extra.confirmation_id='confirmation';
    }
    return {ok:true,status:200,json:async()=>({state:fixtureBtState,...extra})};
  }, {openShortcuts:()=>{}});
</script>
"""
TV_FETCH = """
<script>
window.fetch=async(path)=>{
 let data={};
 if(path==='/api/settings') data={require_pin:false,proxy:{mode:'system'},
   pointer_acceleration:50, magnifier_scale:2.5, magnifier_applied_scale:2.5};
 else if(path==='/api/audio') data={outputs:[],selected:'',volume:50,muted:false};
 else if(path==='/api/display-timer') data={minutes:0,remaining_seconds:0,asleep:false};
 else if(path==='/api/services') data={services:[{id:'example',name:'Пример'}],page_size:12};
 else if(path==='/api/status') data={extension_online:true,pending_commands:0};
 else if(path==='/api/local-pin') data={pin_required:false};
 else if(path==='/api/bluetooth') data={state:{available:true,reason:'',revision:0,
   adapter:{id:'adapter',powered:true,discovering:false},devices:[],remote:null,operation:null},
   lease:'a'.repeat(32)};
 return {ok:true,status:200,json:async()=>data};
};
</script>
"""


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/frame":
            body = (
                b"<!doctype html><style>body{margin:0}iframe{border:0}</style>"
                b'<iframe id="viewport"></iframe>'
            )
            kind = "text/html; charset=utf-8"
        elif self.path in ("/phone", "/tv"):
            name = "remote.html" if self.path == "/phone" else "index.html"
            html = (STATIC / name).read_text()
            if self.path == "/phone":
                html = re.sub(r'<script\s+src="[^"]+"></script>', "", html)
                html = html.replace("</html>", PHONE_FIXTURE + "</html>")
            else:
                html = html.replace(
                    '<script src="/layout.js">', TV_FETCH + '<script src="/layout.js">'
                )
            body = html.encode()
            kind = "text/html; charset=utf-8"
        elif self.path in (
            "/style.css",
            "/bluetooth_controls.css",
            "/layout.js",
            "/launcher_ui.js",
            "/settings_controls.js",
            "/audio_levels.js",
            "/bluetooth_controls.js",
            "/app.js",
        ):
            body = (STATIC / self.path[1:]).read_bytes()
            kind = "text/css; charset=utf-8" if self.path.endswith(".css") else "text/javascript"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def frame(port, session, path, width, height):
    request(port, "POST", f"/session/{session}/frame", {"id": None})
    execute(
        port,
        session,
        """
        const f=document.querySelector('#viewport');
        f.style.width=arguments[1]+'px'; f.style.height=arguments[2]+'px'; f.src=arguments[0];
    """,
        path,
        width,
        height,
    )
    wait_until(
        lambda: execute(
            port,
            session,
            """
        const f=document.querySelector('#viewport');
        return f.contentDocument && f.contentDocument.readyState==='complete' &&
          f.contentDocument.location.pathname===arguments[0];
    """,
            path,
        )
    )
    element = execute(port, session, "return document.querySelector('#viewport');")
    request(port, "POST", f"/session/{session}/frame", {"id": element})
    assert execute(port, session, "return [innerWidth, innerHeight];") == [width, height]


def save_screenshot(port, session, name):
    output = os.environ.get("AD_TV_SETTINGS_SCREENSHOTS")
    if output:
        image = request(port, "GET", f"/session/{session}/screenshot")
        Path(output, name).write_bytes(base64.b64decode(image))


def test_phone_and_tv_settings_geometry():
    assert shutil.which("firefox") and shutil.which("geckodriver")
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = free_port()
    env = dict(os.environ, MOZ_HEADLESS_WIDTH="1360", MOZ_HEADLESS_HEIGHT="1000")
    snap_home = Path.home() / "snap/firefox/common"
    profile_parent = snap_home if snap_home.is_dir() else None
    session = None
    driver = None
    try:
        with tempfile.TemporaryDirectory(
            prefix="ad-tv-settings-layout-", dir=profile_parent
        ) as temp:
            driver = subprocess.Popen(
                [
                    "geckodriver",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--allow-system-access",
                    "--profile-root",
                    temp,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                wait_until(lambda: request(port, "GET", "/status")["ready"])
                session = request(
                    port,
                    "POST",
                    "/session",
                    {
                        "capabilities": {
                            "alwaysMatch": {
                                "browserName": "firefox",
                                "moz:firefoxOptions": {"args": ["-headless"]},
                            }
                        }
                    },
                    timeout=90,
                )["sessionId"]
                base = f"http://127.0.0.1:{server.server_port}"
                request(port, "POST", f"/session/{session}/url", {"url": base + "/frame"})
                # 256 CSS px represents a 320 px phone at 125% page zoom.
                for width in (256, 320, 360, 390):
                    frame(port, session, "/phone", width, 700)
                    execute(
                        port,
                        session,
                        """
                        document.querySelector('#controls').hidden = false;
                        document.querySelector('#remote-face').hidden = true;
                        document.querySelector('#remote-settings-page').hidden = false;
                        document.querySelector('#phone-shortcuts-details').open = true;
                        document.querySelector('#phone-bluetooth-details').open = true;
                        document.querySelector('#connecting').hidden = true;
                        fixtureBt.activate();
                    """,
                    )
                    wait_until(
                        lambda: execute(
                            port,
                            session,
                            """
                        return !!document.querySelector('[data-bt-key="pair"]:not(:disabled)');
                    """,
                        )
                    )
                    execute(port, session, "document.querySelector('[data-bt-key=pair]').click();")
                    wait_until(
                        lambda: execute(
                            port,
                            session,
                            """
                        return !!document.querySelector('.bt-challenge input');
                    """,
                        )
                    )
                    result = execute(
                        port,
                        session,
                        """
                        const root = document.querySelector('#remote-settings-page');
                        const items = [...root.querySelectorAll('button,summary,input,select')]
                          .filter(el => el.getClientRects().length && !el.closest('[hidden]'))
                          .filter(el => !el.closest('details:not([open])') ||
                            (el.tagName==='SUMMARY' &&
                             el.parentElement===el.closest('details:not([open])')));
                        const off = items.filter(el => {
                          const r=el.getBoundingClientRect();
                          return r.left < -0.5 || r.right > innerWidth + 0.5;
                        }).map(el => el.id || el.dataset.shortcut ||
                          el.textContent.trim().slice(0,40));
                        const small = items.filter(el => el.matches('button,summary') &&
                          el.getBoundingClientRect().height < 43)
                          .map(el => el.textContent.trim().slice(0,40));
                        const unreachable = [];
                        for (const el of items) {
                          el.scrollIntoView({block:'center'});
                          const r=el.getBoundingClientRect();
                          if (r.top < -0.5 || r.bottom > innerHeight+0.5)
                            unreachable.push(el.id || el.dataset.shortcut ||
                              el.textContent.slice(0,30));
                        }
                        const save = root.querySelector('[data-shortcut=save]');
                        save.scrollIntoView({block:'center'}); save.focus();
                        const r=save.getBoundingClientRect();
                        return {docWidth:document.documentElement.scrollWidth,
                          width:innerWidth,off,small,unreachable,focused:document.activeElement===save,
                          reachable:r.top>=0&&r.bottom<=innerHeight};
                    """,
                    )
                    assert result["docWidth"] <= result["width"] + 1, result
                    assert not result["off"] and not result["small"], result
                    assert not result["unreachable"], result
                    assert result["focused"] and result["reachable"], result
                    execute(
                        port,
                        session,
                        """
                        fixtureBtState.operation=null;
                        fixtureBtState.devices[0].paired=true;
                        fixtureBt.state=fixtureBtState;
                        fixtureBt.challenge=null;
                        fixtureBt.render();
                        document.querySelector('[data-bt-key=forget_prepare]').click();
                    """,
                    )
                    wait_until(
                        lambda: execute(
                            port,
                            session,
                            """
                        return !!document.querySelector('.bt-confirm');
                    """,
                        )
                    )
                    confirmation = execute(
                        port,
                        session,
                        """
                        const el=document.querySelector('.bt-confirm');
                        const r=el.getBoundingClientRect();
                        return {left:r.left,right:r.right,width:innerWidth,text:el.textContent};
                    """,
                    )
                    assert confirmation["left"] >= -0.5 and confirmation["right"] <= width + 0.5
                    assert "Общие кнопки ТВ-режима останутся" in confirmation["text"]
                    if width == 390:
                        execute(port, session, "window.scrollTo(0,0)")
                        save_screenshot(port, session, "phone.png")
                        execute(
                            port,
                            session,
                            """
                            document.querySelector('#phone-shortcuts-details')
                              .scrollIntoView({block:'start'});
                        """,
                        )
                        save_screenshot(port, session, "phone-buttons.png")
                # 1088×614 is the logical CSS viewport of a 1360×768 display at 125%.
                for width, height in ((1360, 768), (1088, 614)):
                    frame(port, session, "/tv", width, height)
                    wait_until(
                        lambda: execute(
                            port,
                            session,
                            """
                        return typeof document.querySelector('#system-button').onclick==='function';
                    """,
                        )
                    )
                    navigation = execute(
                        port,
                        session,
                        """
                        document.querySelector('#system-button').click();
                        const initial=document.activeElement.id;
                        document.dispatchEvent(new KeyboardEvent('keydown',
                          {key:'ArrowDown',bubbles:true}));
                        return {initial,next:document.activeElement.id,
                          visible:!document.querySelector('#settings').hidden};
                    """,
                    )
                    assert navigation["visible"] and navigation["initial"] == "settings-back"
                    assert navigation["next"] != navigation["initial"]
                    execute(
                        port, session, "document.querySelector('#tv-bluetooth-details').open=true;"
                    )
                    result = execute(
                        port,
                        session,
                        """
                        const root = document.querySelector('#settings');
                        const elements = [...root.querySelectorAll('button,summary,input,select')]
                          .filter(el => el.getClientRects().length && !el.closest('[hidden]'))
                          .filter(el => !el.closest('details:not([open])') ||
                            (el.tagName==='SUMMARY' &&
                             el.parentElement===el.closest('details:not([open])')));
                        const off = elements.filter(el => {const r=el.getBoundingClientRect();
                          return r.left < -0.5 || r.right > innerWidth + 0.5;
                        }).map(el => el.id || el.textContent.trim().slice(0,40));
                        const unreachable=[];
                        for (const el of elements) {
                          el.scrollIntoView({block:'center'});
                          const r=el.getBoundingClientRect();
                          if (r.top < -0.5 || r.bottom > innerHeight+0.5)
                            unreachable.push(el.id || el.textContent.slice(0,30));
                        }
                        const target = root.querySelector('[data-role=browser-locale]');
                        target.scrollIntoView({block:'center'}); target.focus();
                        const r=target.getBoundingClientRect();
                        return {width:innerWidth,docWidth:document.documentElement.scrollWidth,
                          off,unreachable,focused:document.activeElement===target,
                          reachable:r.top>=0&&r.bottom<=innerHeight};
                    """,
                    )
                    assert result["docWidth"] <= result["width"] + 1, result
                    assert not result["off"] and not result["unreachable"], result
                    assert result["focused"] and result["reachable"], result
                    if width == 1360:
                        execute(port, session, "window.scrollTo(0,0)")
                        save_screenshot(port, session, "tv.png")
            finally:
                if session is not None:
                    try:
                        request(port, "DELETE", f"/session/{session}")
                    except Exception:
                        pass
                if driver is not None:
                    driver.terminate()
                    driver.wait(timeout=10)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
