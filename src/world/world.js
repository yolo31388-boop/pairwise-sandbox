class World {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.blocks = Array.from({ length: height }, () => Array(width).fill(null));
  }

  inBounds(x, y) {
    return x >= 0 && x < this.width && y >= 0 && y < this.height;
  }

  getBlock(x, y) {
    if (!this.inBounds(x, y)) return { solid: true, type: 'boundary' };
    return this.blocks[y][x];
  }

  setBlock(x, y, block) {
    if (this.inBounds(x, y)) this.blocks[y][x] = block;
  }

  isSupported(x, y) {
    const below = this.getBlock(x, y + 1);
    return below !== null && below !== undefined;
  }

  placeBlock(x, y, block) {
    if (!this.inBounds(x, y)) {
      throw new Error(`cannot place block outside world at ${x},${y}`);
    }
    if (this.getBlock(x, y) !== null) {
      throw new Error(`cell ${x},${y} is already occupied`);
    }
    // 只有特定方块类型（needsSupport）才强制要求支撑，其余方块（如石头）允许悬空
    if (block && block.needsSupport && !this.isSupported(x, y)) {
      throw new Error(`block ${block.type || 'unknown'} has no support at ${x},${y}`);
    }
    this.setBlock(x, y, block);
  }

  breakBlock(x, y) {
    if (!this.inBounds(x, y)) return null;
    const block = this.getBlock(x, y);
    if (block === null) return null;
    this.setBlock(x, y, null);
    if (block.type === 'tnt') {
      this.explode(x, y, block.blastRadius || 4);
    }
    this.updateNeighbors(x, y);
    return block;
  }

  // 破坏后更新周围：失去支撑且需要支撑的方块连锁脱落；
  // 重力方块由 BlockPhysics 在下一 tick 自然下落
  updateNeighbors(x, y) {
    const above = this.getBlock(x, y - 1);
    if (above && above.needsSupport && !this.isSupported(x, y - 1)) {
      this.breakBlock(x, y - 1);
    }
  }

  // 爆炸按射线逐步推进：遇到抗爆方块即停止该方向，不能穿墙
  explode(x, y, radius) {
    const destroyed = new Set();
    const rays = 16;
    for (let i = 0; i < rays; i++) {
      const angle = (i / rays) * Math.PI * 2;
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);
      for (let r = 0.5; r <= radius; r += 0.5) {
        const cx = Math.round(x + dx * r);
        const cy = Math.round(y + dy * r);
        if (!this.inBounds(cx, cy)) break;
        const block = this.blocks[cy][cx];
        if (block === null) continue;
        if (block.blastResistant || block.indestructible) break;
        destroyed.add(`${cx},${cy}`);
      }
    }
    for (const key of destroyed) {
      const [cx, cy] = key.split(',').map(Number);
      this.blocks[cy][cx] = null;
    }
    return destroyed.size;
  }
}

module.exports = { World };
