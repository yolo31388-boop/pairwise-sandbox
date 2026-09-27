class World {
  constructor(width, height) {
    this.width = width; this.height = height;
    this.blocks = Array.from({length:height}, () => Array(width).fill(null));
  }

  getBlock(x, y) {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return {solid: true, type: 'boundary', unbreakable: true};
    return this.blocks[y][x];
  }

  setBlock(x, y, block) {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height) this.blocks[y][x] = block;
  }

  hasSupport(x, y) {
    return this.getBlock(x, y + 1) !== null;
  }

  placeBlock(x, y, block) {
    if (this.getBlock(x, y) !== null) throw new Error(`位置 (${x}, ${y}) 已被占用`);
    // 需要支撑的方块不能悬空放置
    if (block && block.needsSupport && !this.hasSupport(x, y)) {
      throw new Error(`方块 ${block.type || 'unknown'} 需要支撑，不能放置在 (${x}, ${y})`);
    }
    this.setBlock(x, y, block);
  }

  breakBlock(x, y) {
    const block = this.getBlock(x, y);
    if (!block || block.unbreakable) return null;
    this.setBlock(x, y, null);
    if (block.type === 'tnt' || block.explosive) {
      this.explode(x, y, block.radius || 2);
    }
    // 破坏后更新上方方块状态：失去支撑的重力方块立即沉降，不留悬空
    this.settleColumn(x, y - 1);
    return block;
  }

  // 爆炸沿 8 个方向射线传播，遇到不可破坏方块（墙）即停止，不穿墙
  explode(cx, cy, radius) {
    const dirs = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];
    for (const [dx, dy] of dirs) {
      for (let i = 1; i <= radius; i++) {
        const b = this.getBlock(cx + dx * i, cy + dy * i);
        if (b === null) continue;
        if (b.unbreakable) break;
        this.setBlock(cx + dx * i, cy + dy * i, null);
      }
    }
  }

  // 让某一列中失去支撑的重力方块分步下落，直到落在碰撞面上
  settleColumn(x, fromY) {
    for (let y = Math.min(fromY, this.height - 1); y >= 0; y--) {
      const block = this.getBlock(x, y);
      if (!block) continue;
      if (!block.gravity) break; // 静态方块为上方提供支撑
      let cy = y;
      while (this.getBlock(x, cy + 1) === null) {
        this.setBlock(x, cy + 1, block);
        this.setBlock(x, cy, null);
        cy++;
      }
    }
  }
}

module.exports = { World };
