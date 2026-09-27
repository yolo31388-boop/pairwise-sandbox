const { World } = require('../src/world/world.js');
const { BlockPhysics } = require('../src/world/blockPhysics.js');
const { Liquid } = require('../src/blocks/liquid.js');

function countBlocks(world, predicate) {
  let n = 0;
  for (let y = 0; y < world.height; y++) {
    for (let x = 0; x < world.width; x++) {
      const b = world.getBlock(x, y);
      if (b && predicate(b)) n++;
    }
  }
  return n;
}

describe('沙盒方块物理', () => {
  test('分步下落不穿墙', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, { type: 'sand', gravity: true });
    world.setBlock(5, 10, { type: 'stone', gravity: false });
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 9)).not.toBeNull();
    expect(world.getBlock(5, 10)).not.toBeNull();
    // 沙块必须停在石头上方，且全图只有一个沙块（未穿透、未复制）
    expect(world.getBlock(5, 9).type).toBe('sand');
    expect(countBlocks(world, b => b.type === 'sand')).toBe(1);
  });

  test('碰撞停在面上', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, { type: 'sand', gravity: true });
    world.setBlock(5, 5, { type: 'stone', gravity: false });
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 4)?.type).toBe('sand');
    // 不嵌入：石头所在格仍然是石头
    expect(world.getBlock(5, 5)?.type).toBe('stone');
  });

  test('沙块落地面', () => {
    const world = new World(10, 20);
    world.setBlock(2, 0, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 25; i++) phys.update();
    expect(world.getBlock(2, 19)?.type).toBe('sand');
    // 不会穿出世界底部
    expect(countBlocks(world, b => b.type === 'sand')).toBe(1);
  });

  test('更新顺序从下往上', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, { type: 'sand', gravity: true });
    world.setBlock(5, 1, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    phys.update(); // 只更新一次：下方先动让出格子，上方跟着动
    expect(world.getBlock(5, 0)).toBeNull();
    expect(world.getBlock(5, 1)?.type).toBe('sand');
    expect(world.getBlock(5, 2)?.type).toBe('sand');
  });

  test('方块堆叠支撑', () => {
    const world = new World(10, 20);
    world.setBlock(5, 19, { type: 'sand', gravity: true }); // 已落地（底部）的沙
    world.setBlock(5, 0, { type: 'sand', gravity: true });  // 高处落下
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    // 落在上一个沙块顶上，互不穿透
    expect(world.getBlock(5, 19)?.type).toBe('sand');
    expect(world.getBlock(5, 18)?.type).toBe('sand');
    expect(world.getBlock(5, 17)).toBeNull();
    expect(countBlocks(world, b => b.type === 'sand')).toBe(2);
  });

  test('下落方块落在下落方块上（支撑传递）', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, { type: 'sand', gravity: true });
    world.setBlock(5, 3, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    // 两个同时下落的方块最终堆叠在底部，数量守恒
    expect(world.getBlock(5, 19)?.type).toBe('sand');
    expect(world.getBlock(5, 18)?.type).toBe('sand');
    expect(countBlocks(world, b => b.type === 'sand')).toBe(2);
  });

  test('下方移除上方下落', () => {
    const world = new World(10, 20);
    world.setBlock(5, 5, { type: 'stone', gravity: false });
    world.setBlock(5, 4, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    world.setBlock(5, 5, null);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 19)?.type).toBe('sand');
  });

  test('多方块同时下落', () => {
    const world = new World(10, 20);
    for (let x = 3; x < 7; x++) world.setBlock(x, 0, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    for (let x = 3; x < 7; x++) expect(world.getBlock(x, 19)).not.toBeNull();
    expect(countBlocks(world, b => b.type === 'sand')).toBe(4);
  });

  test('放置支撑检测', () => {
    const world = new World(10, 20);
    expect(() => world.placeBlock(5, 5, { type: 'sand', gravity: true, needsSupport: true })).toThrow();
    // 有支撑时可以放置
    world.setBlock(5, 6, { type: 'stone', gravity: false });
    expect(() => world.placeBlock(5, 5, { type: 'sand', gravity: true, needsSupport: true })).not.toThrow();
    expect(world.getBlock(5, 5)?.type).toBe('sand');
    // 不允许放置在已占据的格子上
    expect(() => world.placeBlock(5, 5, { type: 'stone' })).toThrow();
    // 不需要支撑的特定方块类型允许悬空
    expect(() => world.placeBlock(2, 2, { type: 'stone', gravity: false })).not.toThrow();
  });

  test('破坏更新周围', () => {
    const world = new World(10, 20);
    world.setBlock(5, 10, { type: 'stone', gravity: false });
    world.setBlock(5, 9, { type: 'torch', needsSupport: true });
    world.setBlock(5, 8, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    world.breakBlock(5, 10);
    // 依赖支撑的火把立即脱落，不留悬空方块
    expect(world.getBlock(5, 9)).toBeNull();
    // 重力方块随后下落到底部
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 19)?.type).toBe('sand');
    expect(world.getBlock(5, 10)).toBeNull();
  });

  test('爆炸范围不穿墙', () => {
    const world = new World(10, 20);
    world.setBlock(5, 10, { type: 'tnt', blastRadius: 3 });
    world.setBlock(5, 9, { type: 'stone' });
    world.setBlock(5, 8, { type: 'obsidian', blastResistant: true });
    world.setBlock(5, 7, { type: 'stone' });
    world.setBlock(6, 10, { type: 'stone' });
    const removed = world.breakBlock(5, 10);
    expect(removed?.type).toBe('tnt');
    // 范围内普通方块被摧毁
    expect(world.getBlock(5, 9)).toBeNull();
    expect(world.getBlock(6, 10)).toBeNull();
    // 抗爆方块本身不被摧毁，且挡住爆炸保护后方方块
    expect(world.getBlock(5, 8)?.type).toBe('obsidian');
    expect(world.getBlock(5, 7)?.type).toBe('stone');
  });

  test('液体流动', () => {
    const world = new World(10, 20);
    world.setBlock(5, 5, new Liquid());
    const l = world.getBlock(5, 5);
    l.update(world, 5, 5);
    expect(world.getBlock(5, 6)).not.toBeNull();
    expect(world.getBlock(5, 6).type).toBe('liquid');
  });

  test('液体源方块不消失且向下扩散', () => {
    const world = new World(10, 20);
    world.setBlock(5, 5, new Liquid());
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 20; i++) phys.update();
    const source = world.getBlock(5, 5);
    expect(source?.type).toBe('liquid');
    expect(source.level).toBe(8);
    expect(source.source).toBe(true);
    // 向下形成水柱直到底部
    expect(world.getBlock(5, 19)?.type).toBe('liquid');
  });

  test('液体向四周扩散且水位递减、不穿固体', () => {
    const world = new World(10, 20);
    for (let x = 0; x < 10; x++) world.setBlock(x, 10, { type: 'stone', gravity: false });
    world.setBlock(5, 5, new Liquid());
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 25; i++) phys.update();
    // 落到地面后向两侧扩散
    expect(world.getBlock(4, 9)?.type).toBe('liquid');
    expect(world.getBlock(6, 9)?.type).toBe('liquid');
    // 水位随扩散递减
    expect(world.getBlock(4, 9).level).toBeLessThan(8);
    // 不穿透固体地板
    expect(world.getBlock(5, 10)?.type).toBe('stone');
    expect(world.getBlock(5, 11)).toBeNull();
  });

  test('沙块在液体中下沉而不穿透', () => {
    const world = new World(10, 20);
    world.setBlock(5, 15, new Liquid());
    world.setBlock(5, 0, { type: 'sand', gravity: true });
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    // 沙块沉到底部，液体被置换到上方，两者数量守恒
    expect(world.getBlock(5, 19)?.type).toBe('sand');
    expect(countBlocks(world, b => b.type === 'sand')).toBe(1);
    expect(countBlocks(world, b => b.type === 'liquid')).toBeGreaterThan(0);
  });
});
