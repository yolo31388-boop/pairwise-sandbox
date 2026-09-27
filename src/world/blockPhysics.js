class BlockPhysics {
  constructor(world) { this.world = world; }

  update() {
    // 从下往上更新：下方方块先移动，堆叠方块才能正确传递支撑
    for (let y = this.world.height - 1; y >= 0; y--) {
      for (let x = 0; x < this.world.width; x++) {
        const block = this.world.getBlock(x, y);
        if (!block) continue;
        if (block.gravity) {
          this.stepFall(x, y, block);
        } else if (block.type === 'liquid' && typeof block.update === 'function') {
          block.update(this.world, x, y);
        }
      }
    }
  }

  // 分步下落：每次 update 只移动一格，并检测下一格碰撞
  stepFall(x, y, block) {
    const below = this.world.getBlock(x, y + 1);
    if (below === null) {
      this.world.setBlock(x, y + 1, block);
      this.world.setBlock(x, y, null);
    }
    // 下方被占用（固体或另一个下落方块）时停在碰撞面上，不嵌入不穿透
  }
}

module.exports = { BlockPhysics };
