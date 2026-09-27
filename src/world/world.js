
class World {
  constructor(width, height) {
    this.width = width; this.height = height;
    this.blocks = Array.from({length:height}, () => Array(width).fill(null));
  }
  getBlock(x, y) {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return {solid: true};
    return this.blocks[y][x];
  }
  setBlock(x, y, block) {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height) this.blocks[y][x] = block;
  }
  placeBlock(x, y, block) {
    // BUG: 不检测支撑
    this.setBlock(x, y, block);
  }
}

module.exports = { World };
