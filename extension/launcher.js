if (location.href === "http://127.0.0.1:8765/") {
  browser.runtime.onMessage.addListener(({command}) => {
    if (command === "ok") {
      const service_id = document.activeElement?.dataset?.serviceId;
      if (service_id) return {service_id};
      document.dispatchEvent(new KeyboardEvent("keydown", {key:"Enter", bubbles:true}));
      return {service_id:null};
    }
    const map = {up:"ArrowUp", down:"ArrowDown", left:"ArrowLeft", right:"ArrowRight"};
    if (map[command]) document.dispatchEvent(new KeyboardEvent("keydown", {key:map[command], bubbles:true}));
    return {service_id:null};
  });
  const pulse = () => browser.runtime.sendMessage({type:"launcher-pulse"}).catch(() => {});
  pulse();
  setInterval(pulse, 1000);
}
