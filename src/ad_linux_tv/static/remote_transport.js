"use strict";

class RemoteTransport {
  constructor(location) {
    const address = new URL("/api/remote-ws", location.href);
    address.protocol = address.protocol === "https:" ? "wss:" : "ws:";
    this.address = address.href;
    this.socket = null;
    this.connecting = null;
    this.connectReject = null;
    this.csrf = "";
    this.nextId = 1;
    this.pending = new Map();
  }

  close() {
    const socket = this.socket;
    const rejectConnect = this.connectReject;
    this.socket = null;
    this.connecting = null;
    this.connectReject = null;
    if (rejectConnect) rejectConnect(new Error("remote connection closed"));
    if (socket) socket.close();
    for (const item of this.pending.values()) {
      clearTimeout(item.timer);
      item.reject(new Error("remote connection closed"));
    }
    this.pending.clear();
  }

  connect(csrf) {
    if (this.socket?.readyState === WebSocket.OPEN && this.csrf === csrf)
      return Promise.resolve();
    if (this.connecting && this.csrf === csrf) return this.connecting;
    this.close();
    this.csrf = csrf;
    const socket = new WebSocket(this.address, `csrf.${csrf}`);
    this.socket = socket;
    this.connecting = new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (this.socket === socket) this.close();
      }, 6000);
      this.connectReject = error => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      };
      const fail = () => {
        if (this.socket !== socket) return;
        this.close();
      };
      socket.onopen = () => {
        if (this.socket !== socket) return;
        settled = true;
        clearTimeout(timer);
        this.connectReject = null;
        this.connecting = null;
        resolve();
      };
      socket.onerror = fail;
      socket.onclose = fail;
      socket.onmessage = event => {
        let reply;
        try { reply = JSON.parse(event.data); } catch (_) { return; }
        const item = this.pending.get(reply.id);
        if (!item) return;
        this.pending.delete(reply.id);
        clearTimeout(item.timer);
        item.resolve({
          status: reply.status,
          ok: reply.status >= 200 && reply.status < 300,
          json: async () => reply.body,
        });
      };
    });
    return this.connecting;
  }

  async request(csrf, method, path, body = null) {
    if (!csrf) throw new Error("remote session unavailable");
    await this.connect(csrf);
    if (this.pending.size >= 32) throw new Error("remote queue full");
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("remote response timed out"));
        this.close();
      }, 6000);
      this.pending.set(id, {resolve, reject, timer});
      try { this.socket.send(JSON.stringify({id, method, path, body})); }
      catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }
}

if (typeof module !== "undefined") module.exports = {RemoteTransport};
