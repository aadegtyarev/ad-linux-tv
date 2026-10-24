"use strict";
(function (root, factory) {
  const layout = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = layout;
  if (root) root.MediaLayout = layout;
})(typeof globalThis === "undefined" ? this : globalThis, function () {
  function pageCount(total, size) {
    if (!Number.isInteger(total) || total < 0 || !Number.isInteger(size) || size < 1) {
      throw new RangeError("invalid page dimensions");
    }
    return Math.max(1, Math.ceil(total / size));
  }
  function pageItems(items, page, size) {
    const pages = pageCount(items.length, size);
    if (!Number.isInteger(page) || page < 0 || page >= pages) throw new RangeError("page out of range");
    return items.slice(page * size, (page + 1) * size);
  }
  function moveFocus(index, direction, total, columns) {
    if (!Number.isInteger(index) || index < 0 || index >= total || !Number.isInteger(columns) || columns < 1) {
      throw new RangeError("invalid grid focus");
    }
    if (direction === "left") return (index + total - 1) % total;
    if (direction === "right") return (index + 1) % total;
    if (direction !== "up" && direction !== "down") throw new RangeError("invalid direction");
    const rows = Math.ceil(total / columns), row = Math.floor(index / columns), col = index % columns;
    const next = (row + rows + (direction === "down" ? 1 : -1)) % rows;
    return Math.min(next * columns + col, total - 1);
  }
  return {pageCount, pageItems, moveFocus};
});
