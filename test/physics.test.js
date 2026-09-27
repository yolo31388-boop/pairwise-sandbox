const { World } = require('../src/world/world.js');
const { BlockPhysics } = require('../src/world/blockPhysics.js');
const { Liquid } = require('../src/blocks/liquid.js');

describe('沙盒方块物理', () => {
  test('分步下落不穿墙', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, {type:'sand', gravity:true});
    world.setBlock(5, 10, {type:'stone', gravity:false});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 9)).not.toBeNull();
    expect(world.getBlock(5, 10)).not.toBeNull();
  });

  test('分步下落每帧只移动一格', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    phys.update();
    expect(world.getBlock(5, 1)?.type).toBe('sand');
    expect(world.getBlock(5, 0)).toBeNull();
    phys.update();
    expect(world.getBlock(5, 2)?.type).toBe('sand');
  });

  test('碰撞停在面上', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, {type:'sand', gravity:true});
    world.setBlock(5, 5, {type:'stone', gravity:false});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 4)?.type).toBe('sand');
  });

  test('沙块落地面', () => {
    const world = new World(10, 20);
    world.setBlock(3, 0, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    expect(world.getBlock(3, 19)?.type).toBe('sand');
    expect(world.getBlock(3, 18)).toBeNull();
  });

  test('方块堆叠支撑不互相穿透', () => {
    const world = new World(10, 20);
    world.setBlock(5, 3, {type:'sand', gravity:true});
    world.setBlock(5, 4, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    expect(world.getBlock(5, 18)?.type).toBe('sand');
    expect(world.getBlock(5, 19)?.type).toBe('sand');
    // 两个方块占据两个不同格子，没有合并或丢失
    let count = 0;
    for (let y = 0; y < 20; y++) if (world.getBlock(5, y)) count++;
    expect(count).toBe(2);
  });

  test('下落方块落在下落方块上传递支撑', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, {type:'sand', gravity:true});
    world.setBlock(5, 5, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    expect(world.getBlock(5, 18)?.type).toBe('sand');
    expect(world.getBlock(5, 19)?.type).toBe('sand');
  });

  test('更新顺序从下往上，堆叠整体下移', () => {
    const world = new World(10, 20);
    world.setBlock(5, 4, {type:'sand', gravity:true});
    world.setBlock(5, 5, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    phys.update();
    // 从下往上：下方先落到 6，上方再落到 5，堆叠保持紧凑
    expect(world.getBlock(5, 5)?.type).toBe('sand');
    expect(world.getBlock(5, 6)?.type).toBe('sand');
    expect(world.getBlock(5, 4)).toBeNull();
  });

  test('下方移除上方下落', () => {
    const world = new World(10, 20);
    world.setBlock(5, 5, {type:'stone', gravity:false});
    world.setBlock(5, 4, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    world.setBlock(5, 5, null);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 19)?.type).toBe('sand');
  });

  test('液体流动', () => {
    const world = new World(10, 20);
    world.setBlock(5, 5, new Liquid());
    const l = world.getBlock(5, 5);
    l.update(world, 5, 5);
    expect(world.getBlock(5, 6)).not.toBeNull();
  });

  test('液体源方块保留且液位不变', () => {
    const world = new World(10, 20);
    world.setBlock(5, 5, new Liquid());
    world.getBlock(5, 5).update(world, 5, 5);
    const source = world.getBlock(5, 5);
    expect(source?.type).toBe('liquid');
    expect(source.level).toBe(8);
    expect(world.getBlock(5, 6)?.type).toBe('liquid');
  });

  test('液体在地面向两侧扩散且液位递减', () => {
    const world = new World(10, 20);
    for (let x = 0; x < 10; x++) world.setBlock(x, 19, {type:'stone', gravity:false});
    world.setBlock(5, 18, new Liquid());
    world.getBlock(5, 18).update(world, 5, 18);
    expect(world.getBlock(4, 18)?.type).toBe('liquid');
    expect(world.getBlock(6, 18)?.type).toBe('liquid');
    expect(world.getBlock(4, 18).level).toBe(7);
  });

  test('液体通过物理更新持续流动', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, new Liquid());
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 25; i++) phys.update();
    expect(world.getBlock(5, 19)?.type).toBe('liquid');
  });

  test('放置支撑检测', () => {
    const world = new World(10, 20);
    expect(() => world.placeBlock(5, 5, {type:'sand', gravity:true, needsSupport:true})).toThrow();
  });

  test('放置支撑检测：有支撑时成功', () => {
    const world = new World(10, 20);
    expect(() => world.placeBlock(5, 19, {type:'sand', gravity:true, needsSupport:true})).not.toThrow();
    world.setBlock(3, 10, {type:'stone', gravity:false});
    expect(() => world.placeBlock(3, 9, {type:'sand', gravity:true, needsSupport:true})).not.toThrow();
    expect(world.getBlock(3, 9)?.type).toBe('sand');
  });

  test('破坏方块后上方方块下落不留悬空', () => {
    const world = new World(10, 20);
    world.setBlock(5, 10, {type:'stone', gravity:false});
    world.setBlock(5, 9, {type:'sand', gravity:true});
    const broken = world.breakBlock(5, 10);
    expect(broken?.type).toBe('stone');
    expect(world.getBlock(5, 10)).toBeNull();
    expect(world.getBlock(5, 19)?.type).toBe('sand');
    expect(world.getBlock(5, 9)).toBeNull();
  });

  test('爆炸范围正确且不穿墙', () => {
    const world = new World(10, 20);
    world.setBlock(5, 10, {type:'tnt', gravity:false, explosive:true, radius:2});
    world.setBlock(5, 8, {type:'stone', gravity:false});   // 范围内，应被摧毁
    world.setBlock(3, 10, {type:'stone', gravity:false});  // 范围内，应被摧毁
    world.setBlock(2, 10, {type:'stone', gravity:false});  // 超出半径，应保留
    world.setBlock(6, 10, {type:'bedrock', gravity:false, unbreakable:true}); // 墙
    world.setBlock(7, 10, {type:'stone', gravity:false});  // 墙后，应保留
    world.breakBlock(5, 10);
    expect(world.getBlock(5, 10)).toBeNull();
    expect(world.getBlock(5, 8)).toBeNull();
    expect(world.getBlock(3, 10)).toBeNull();
    expect(world.getBlock(2, 10)?.type).toBe('stone');
    expect(world.getBlock(6, 10)?.type).toBe('bedrock');
    expect(world.getBlock(7, 10)?.type).toBe('stone');
  });

  test('多方块同时下落', () => {
    const world = new World(10, 20);
    for (let x = 3; x < 7; x++) world.setBlock(x, 0, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    for (let x = 3; x < 7; x++) expect(world.getBlock(x, 19)).not.toBeNull();
  });
});
