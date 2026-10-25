"use strict";

function createLauncherUI(send, openSettings) {
  let services = [];
  let size = 12;
  let focus = 0;
  const tiles = document.querySelector("#tiles");
  const systemButton = document.querySelector("#system-button");
  systemButton.dataset.settings = "true";
  systemButton.onclick = openSettings;

  function render(focusButton = false) {
    const page = Math.floor(focus / size);
    const first = page * size;
    tiles.replaceChildren();
    MediaLayout.pageItems(services, page, size).forEach((service, offset) => {
      const index = first + offset;
      const button = document.createElement("button");
      button.textContent = service.name;
      button.dataset.serviceIndex = String(index);
      button.dataset.serviceId = service.id;
      if (service.color) {
        button.classList.add("colored-tile");
        button.style.setProperty("--tile-color", service.color);
      }
      button.tabIndex = index === focus ? 0 : -1;
      button.onfocus = () => setFocus(index);
      button.onclick = () => {
        setFocus(index);
        send("open", service.id);
      };
      tiles.append(button);
    });
    const pages = MediaLayout.pageCount(services.length, size);
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
    const currentPage = Math.floor(focus / size);
    focus = MediaLayout.moveFocus(focus, direction, services.length, columns());
    if (Math.floor(focus / size) === currentPage) {
      setFocus(focus);
      tiles.children[focus - currentPage * size]?.focus();
    } else render(true);
  });

  document.querySelector("#next").onclick = () => {
    const pages = MediaLayout.pageCount(services.length, size);
    setFocus(((Math.floor(focus / size) + 1) % pages) * size);
    render(true);
  };
  document.querySelector("#prev").onclick = () => {
    const pages = MediaLayout.pageCount(services.length, size);
    setFocus(((Math.floor(focus / size) + pages - 1) % pages) * size);
    render(true);
  };

  function selectForBridge() {
    const active = document.activeElement;
    if (active === document.querySelector("#next") || active === document.querySelector("#prev")) {
      active.click();
      return null;
    }
    return services[focus]?.id || null;
  }

  function update(items, pageSize) {
    if (size === pageSize && JSON.stringify(services) === JSON.stringify(items)) return;
    const active = document.activeElement;
    const restoreFocus = tiles.contains(active);
    const selectedId = active?.dataset?.serviceId;
    const previousFocus = focus;
    services = items;
    size = pageSize;
    const selectedIndex = selectedId ? services.findIndex(service => service.id === selectedId) : -1;
    focus = restoreFocus && selectedIndex >= 0
      ? selectedIndex : Math.min(previousFocus, services.length - 1);
    render(restoreFocus);
  }
  return {update, selectForBridge};
}
