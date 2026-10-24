if (location.href === "http://127.0.0.1:8765/") {
  browser.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.command === "ok") {
      document.dispatchEvent(new Event("ad-linux-tv-select-for-bridge"));
      sendResponse({service_id:document.documentElement.dataset.bridgeServiceId || null});
      return false;
    }
    const map = {up:"ArrowUp", down:"ArrowDown", left:"ArrowLeft", right:"ArrowRight"};
    const key = map[message?.command];
    if (!key) return false;
    document.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles:true}));
    sendResponse({service_id:null});
    return false;
  });
  const pulse = () => browser.runtime.sendMessage({type:"launcher-pulse"}).catch(() => {});
  pulse();
  setInterval(pulse, 1000);
}
