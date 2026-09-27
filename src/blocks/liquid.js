class Liquid {
  constructor(level = 8) {
    this.type = 'liquid';
    this.level = level;
    this.source = level >= 8; // 满格液体为源方块，永不消失
    this.gravity = false;
  }

  update(world, x, y) {
    // 优先向下流动，保持原有水位（形成瀑布）
    const below = world.getBlock(x, y + 1);
    if (below === null) {
      const child = new Liquid(this.level);
      child._tick = world._physicsTick;
      world.setBlock(x, y + 1, child);
      return;
    }
    // 下方受阻时向两侧扩散，水位递减，耗尽即停止
    if (this.level <= 1) return;
    for (const dx of [-1, 1]) {
      const side = world.getBlock(x + dx, y);
      if (side === null) {
        const child = new Liquid(this.level - 1);
        child._tick = world._physicsTick;
        world.setBlock(x + dx, y, child);
      }
    }
  }
}

module.exports = { Liquid };
