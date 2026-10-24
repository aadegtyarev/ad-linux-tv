if (location.href === "http://127.0.0.1:8765/") {
  browser.runtime.onMessage.addListener(({command}) => {
    const map = {up:"ArrowUp", down:"ArrowDown", left:"ArrowLeft", right:"ArrowRight", ok:"Enter"};
    if (map[command]) document.dispatchEvent(new KeyboardEvent("keydown", {key:map[command], bubbles:true}));
  });
  const pulse = () => browser.runtime.sendMessage({type:"launcher-pulse"}).catch(() => {});
  pulse();
  setInterval(pulse, 1000);
}
