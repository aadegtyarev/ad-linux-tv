"use strict";

function createLauncherUI(send, openSettings) {
  let services = [];
  let size = 12;
  let focus = 0;
  const tiles = document.querySelector("#tiles");
  const entries = () => [...services, {name: "Система", settings: true}];

  function render(focusButton = false) {
    const page = Math.floor(focus / size);
    const first = page * size;
    tiles.replaceChildren();
    MediaLayout.pageItems(entries(), page, size).forEach((service, offset) => {
      const index = first + offset;
      const button = document.createElement("button");
      button.textContent = service.name;
      button.dataset.serviceIndex = String(index);
      if (service.settings) button.dataset.settings = "true";
      else button.dataset.serviceId = service.id;
      button.tabIndex = index === focus ? 0 : -1;
      button.onfocus = () => setFocus(index);
      button.onclick = () => {
        setFocus(index);
        if (service.settings) openSettings();
        else send("open", service.id);
      };
      tiles.append(button);
    });
    const pages = MediaLayout.pageCount(services.length + 1, size);
    document.querySelector("#page").textContent = `${page + 1} / ${pages}`;
    document.querySelector(".pagination").hidden = pages === 1;
    if (focusButton) tiles.children[focus - first]?.focus();
  }

  function setFocus(index) {
    focus = index;
    for (const button of tiles.children) {
      button.tabIndex = Number(button.dataset.serviceIndex) === focus ? 0 : -1;
    }
  }

  function columns() {
    const tracks = getComputedStyle(tiles).gridTemplateColumns.trim().split(/\s+/);
    return Math.max(1, tracks.filter(Boolean).length);
  }

  tiles.addEventListener("focusin", event => {
    const index = Number(event.target.dataset.serviceIndex);
    if (Number.isInteger(index)) setFocus(index);
  });
  document.addEventListener("keydown", event => {
    const direction = {
      ArrowRight: "right", ArrowLeft: "left", ArrowDown: "down", ArrowUp: "up",
    }[event.key];
    if (!direction || !document.querySelector("#settings").hidden) return;
    event.preventDefault();
    const activeIndex = Number(document.activeElement?.dataset?.serviceIndex);
    if (Number.isInteger(activeIndex)) focus = activeIndex;
    focus = MediaLayout.moveFocus(focus, direction, services.length + 1, columns());
    render(true);
  });

  document.querySelector("#next").onclick = () => {
    const pages = MediaLayout.pageCount(services.length + 1, size);
    focus = ((Math.floor(focus / size) + 1) % pages) * size;
    render(true);
  };
  document.querySelector("#prev").onclick = () => {
    const pages = MediaLayout.pageCount(services.length + 1, size);
    focus = ((Math.floor(focus / size) + pages - 1) % pages) * size;
    render(true);
  };

  function selectForBridge() {
    const active = document.activeElement;
    if (active === document.querySelector("#next") || active === document.querySelector("#prev")) {
      active.click();
      return null;
    }
    if (focus === services.length) {
      Array.from(tiles.children).find(button => button.dataset.settings === "true")?.click();
      return null;
    }
    return services[focus]?.id || null;
  }

  function update(items, pageSize) {
    if (size === pageSize && JSON.stringify(services) === JSON.stringify(items)) return;
    const active = document.activeElement;
    const restoreFocus = tiles.contains(active);
    const selectedId = active?.dataset?.serviceId;
    const wasSettings = active?.dataset?.settings === "true";
    const previousFocus = focus;
    services = items;
    size = pageSize;
    const selectedIndex = selectedId ? services.findIndex(service => service.id === selectedId) : -1;
    focus = wasSettings ? services.length : restoreFocus && selectedIndex >= 0
      ? selectedIndex : Math.min(previousFocus, services.length);
    render(restoreFocus);
  }
  return {update, selectForBridge};
}
