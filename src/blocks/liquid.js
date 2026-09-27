class Liquid {
  constructor(level = 8) {
    this.type = 'liquid';
    this.level = level;
    this.gravity = false;
    this.solid = false;
  }

  update(world, x, y) {
    // 优先向下流动，源方块保留
    if (world.getBlock(x, y + 1) === null) {
      world.setBlock(x, y + 1, new Liquid(this.level));
      return;
    }
    // 下方被占时向两侧扩散，液位递减，流尽即止
    if (this.level > 1) {
      for (const dx of [1, -1]) {
        if (world.getBlock(x + dx, y) === null) {
          world.setBlock(x + dx, y, new Liquid(this.level - 1));
        }
      }
    }
  }
}

module.exports = { Liquid };
