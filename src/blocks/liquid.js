
class Liquid {
  constructor() { this.type = 'liquid'; this.level = 8; }
  update(world, x, y) {
    // BUG: 不流动
  }
}

module.exports = { Liquid };
