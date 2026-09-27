class BlockPhysics {
  constructor(world) {
    this.world = world;
    this.tick = 0;
  }

  update() {
    this.tick++;
    this.world._physicsTick = this.tick;
    // 从下往上更新：下方方块先移动/流动，支撑关系才能正确传递
    for (let y = this.world.height - 1; y >= 0; y--) {
      for (let x = 0; x < this.world.width; x++) {
        const block = this.world.getBlock(x, y);
        if (!block) continue;
        if (block._tick === this.tick) continue; // 本 tick 已处理过（含新生成的液体）
        if (block.gravity) {
          this.stepGravity(x, y, block);
        } else if (block.type === 'liquid' && typeof block.update === 'function') {
          block._tick = this.tick;
          block.update(this.world, x, y);
        }
      }
    }
  }

  // 每 tick 只下落一格（像素分步），每步都做碰撞检测：
  // 下方被占据时停在碰撞面上，不嵌入也不穿透
  stepGravity(x, y, block) {
    const below = this.world.getBlock(x, y + 1);
    if (below === null) {
      this.world.setBlock(x, y + 1, block);
      this.world.setBlock(x, y, null);
      block._tick = this.tick;
    } else if (below.type === 'liquid') {
      // 重物在液体中下沉，与液体交换位置而不是穿透
      this.world.setBlock(x, y + 1, block);
      this.world.setBlock(x, y, below);
      block._tick = this.tick;
      below._tick = this.tick;
    }
    // 其他情况：下方是固体或另一个暂时停住的下落方块，停在碰撞面上
  }
}

module.exports = { BlockPhysics };
