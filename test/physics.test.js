
const { World } = require('../src/world/world.js');
const { BlockPhysics } = require('../src/world/blockPhysics.js');

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
  test('碰撞停在面上', () => {
    const world = new World(10, 20);
    world.setBlock(5, 0, {type:'sand', gravity:true});
    world.setBlock(5, 5, {type:'stone', gravity:false});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 20; i++) phys.update();
    expect(world.getBlock(5, 4)?.type).toBe('sand');
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
    const { Liquid } = require('../src/blocks/liquid.js');
    const world = new World(10, 20);
    world.setBlock(5, 5, new Liquid());
    const l = world.getBlock(5, 5);
    l.update(world, 5, 5);
    expect(world.getBlock(5, 6)).not.toBeNull();
  });
  test('放置支撑检测', () => {
    const world = new World(10, 20);
    expect(() => world.placeBlock(5, 5, {type:'sand', gravity:true, needsSupport:true})).toThrow();
  });
  test('多方块同时下落', () => {
    const world = new World(10, 20);
    for (let x = 3; x < 7; x++) world.setBlock(x, 0, {type:'sand', gravity:true});
    const phys = new BlockPhysics(world);
    for (let i = 0; i < 30; i++) phys.update();
    for (let x = 3; x < 7; x++) expect(world.getBlock(x, 19)).not.toBeNull();
  });
});
