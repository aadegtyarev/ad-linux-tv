"use strict";

class PointerAcceleration {
  constructor(level = 50) {
    this.level = level;
    this.lastTime = null;
    this.lastDx = 0;
    this.lastDy = 0;
    this.speed = 0;
  }

  move(dx, dy, time) {
    const dt = this.lastTime === null ? null : time - this.lastTime;
    const reversed = dx * this.lastDx + dy * this.lastDy < 0;
    if (dt === null || !Number.isFinite(dt) || dt <= 0 || dt > 90 || reversed)
      this.speed = 0;
    else {
      const instant = Math.hypot(dx, dy) / Math.max(dt, 8);
      this.speed = this.speed * 0.2 + instant * 0.8;
    }
    this.lastTime = time;
    this.lastDx = dx;
    this.lastDy = dy;
    const faster = Math.max(0, Math.min(1, (this.speed - 0.08) / 0.75));
    const gain = 3 * (1 + (this.level / 100) * 2 * faster);
    return {dx:dx * gain, dy:dy * gain};
  }
}
