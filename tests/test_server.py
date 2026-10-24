"""HTTP security and endpoint tests."""
import base64
import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from ad_linux_tv.config import DEFAULT_SERVICES
from ad_linux_tv.server import make_handler


def test_http_login_csrf_and_command(tmp_path):
    salt=b"0123456789abcdef"
    auth={"salt":base64.b64encode(salt).decode(), "verifier":base64.b64encode(hashlib.pbkdf2_hmac("sha256",b"1234",salt,310_000)).decode()}
    config={"auth":auth,"services":DEFAULT_SERVICES,"page_size":12,"port":8765}
    server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(config))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    conn=HTTPConnection("127.0.0.1",server.server_port)
    try:
        conn.request("GET","/api/services"); response=conn.getresponse(); assert response.status==200; response.read()
        conn.request("POST","/api/command",body='{"command":"home"}',headers={"Content-Length":"18"})
        assert conn.getresponse().status==403
        body=json.dumps({"pin":"1234"})
        conn.request("POST","/api/login",body=body,headers={"Content-Type":"application/json"})
        response=conn.getresponse(); assert response.status==200
        cookie=response.getheader("Set-Cookie").split(";",1)[0]; response.read()
        body=json.dumps({"command":"open","service_id":"not-allowed"})
        headers={"Content-Type":"application/json","Cookie":cookie,"Origin":f"http://127.0.0.1:{server.server_port}"}
        conn.request("POST","/api/command",body=body,headers=headers)
        assert conn.getresponse().status==400
    finally:
        conn.close(); server.shutdown()
