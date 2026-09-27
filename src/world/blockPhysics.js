
class BlockPhysics {
  constructor(world) { this.world = world; }
  update() {
    for (let y = this.world.height - 1; y >= 0; y--) {
      for (let x = 0; x < this.world.width; x++) {
        const block = this.world.getBlock(x, y);
        if (block && block.gravity) {
          // BUG: 整帧位移一次检测
          const newY = y + 3;
          if (!this.world.getBlock(x, newY)) {
            this.world.setBlock(x, newY, block);
            this.world.setBlock(x, y, null);
          }
        }
      }
    }
  }
}

module.exports = { BlockPhysics };
