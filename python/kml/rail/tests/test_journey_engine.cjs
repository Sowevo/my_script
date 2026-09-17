const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JourneyEngine} = require('../app/static/journey_engine.js');
function setup(ways = {1:[1,2,3],2:[3,4,5],3:[5,6],4:[7,6],8:[8,9]},coords,meta = {},stops = []) {
  const store = {ways:new Map(),coords:new Map(),nodeWays:new Map(),stops:new Set(stops),async ensure(ids) {
    for (const id of ids) assert.ok(this.ways.has(id),'missing '+id);
  }};
  for (const [id,nodes] of Object.entries(ways)) {
    store.ways.set(+id,{nodes,meta:meta[id] || {}});
    for (const n of nodes) {
      store.coords.set(n,coords ? coords[n] : [35,139+n*.001]);
      store.nodeWays.set(n,[...new Set([...(store.nodeWays.get(n) || []),+id])]);
    }
  }
  return new JourneyEngine(store);
}
const ids = data => data.legs.at(-1).path.map(i => i.way_id);
async function firstTwo(e) {
  const first = await e.advance([],{way_id:1});
  return e.advance(first.legs,{way_id:2},true);
}
test('首次与换乘都停在首条；继续允许超过20条',async () => {
  const ways = Object.fromEntries(Array.from({length:62},(_,i) => [i+1,[i+1,i+2]]));
  ways[100]=[1000,1001]; ways[101]=[1001,1002];
  const e=setup(ways);
  const a=await e.advance([],{way_id:1});
  assert.deepEqual(ids(a),[1]);
  const transfer=await e.advance(a.legs,{way_id:100,transfer:true});
  assert.deepEqual(ids(transfer),[100]);
  assert.equal(transfer.legs.length,2);
  const b=await e.advance(a.legs,{way_id:2});
  assert.equal(ids(b).length,62);
  assert.equal(b.path.length,61);
  assert.equal(b.legs[0].path[1].type,'manual');
  assert.equal(b.legs[0].path[2].type,'auto');
});
test('ABC同端共点：手选B后不自动折回C，但C仍可手选',async () => {
  const e=setup({1:[1,2],2:[2,3],3:[2,4]});
  const a=await e.advance([],{way_id:1}),b=await e.advance(a.legs,{way_id:2});
  assert.deepEqual(ids(b),[1,2]); assert.deepEqual(b.choices,[3]);
  assert.equal(b.manual_confirmation_required,true);
  const c=await e.advance(b.legs,{way_id:3},true);
  assert.deepEqual(ids(c),[1,2,3]);
});
test('中途相连与多个共享节点不能自动推进',async () => {
  for (const candidate of [[4,3,5],[2,3,4]]) {
    const e=setup({1:[1,2],2:[2,3],3:candidate});
    const a=await e.advance([],{way_id:1}),b=await e.advance(a.legs,{way_id:2});
    assert.deepEqual(ids(b),[1,2]);assert.equal(b.manual_confirmation_required,true);
  }
});
test('闭环停止；裁掉的起始区间不误判闭环',async () => {
  const e=setup({1:[1,2,3],2:[3,4],3:[4,1],4:[1,5]});
  const a=await e.advance([],{way_id:1}),b=await e.advance(a.legs,{way_id:2});
  assert.deepEqual(ids(b),[1,2,3]);assert.deepEqual(b.choices,[]);
  const start=await e.start([],{way_id:1,point:[35,139.002],direction:1});
  const c=await e.advance(start.legs,{way_id:2});
  assert.deepEqual(ids(c),[1,2,3,4]);
});
test('部分轨道保留区间内的身后分支不能自动推进',async () => {
  const e=setup({1:[1,2,3],2:[2,4]});
  const a=await e.start([],{way_id:1,point:[35,139.0015],direction:1});
  assert.deepEqual(a.choices,[2]);assert.equal(e.canAuto(a.legs[0],2),false);
});
test('从中间way结束移除后续；退回只缩短；前进只补余段',async () => {
  const e=setup(),a=await firstTwo(e),b=await e.advance(a.legs,{way_id:3},true);
  const c=await e.cut(b.legs,{point:[35,139.0045]});
  assert.deepEqual(ids(c),[1,2]);
  assert.ok(Math.abs(c.total_path_coords.at(-1).coords.at(-1)[1]-139.0045)<1e-8);
  const forward=await e.advance(c.legs,{way_id:2},true);
  assert.deepEqual(ids(forward),[1,2,2]);
  assert.deepEqual((await e.undo(forward.legs)).legs,c.legs);
  assert.deepEqual(ids(await e.undo(c.legs)),[1]);
  assert.deepEqual(ids(b),[1,2,3],'原行程不被草稿修改');
});
test('反向裁剪、单way中间保留与部分轨道逐条退回',async () => {
  const e=setup();
  let a=await e.advance([],{way_id:4});
  a=await e.advance(a.legs,{way_id:3},true);
  const c=await e.cut(a.legs,{point:[35,139.0055]});
  assert.ok(c.legs[0].path.at(-1).span[0]>c.legs[0].path.at(-1).span[1]);
  const start=await e.start([],{way_id:1,point:[35,139.0015],direction:1});
  const cut=await e.cut(start.legs,{point:[35,139.0025]});
  const line=cut.total_path_coords[0].coords;
  assert.ok(Math.abs(line[0][1]-139.0015)<1e-8);
  assert.ok(Math.abs(line.at(-1)[1]-139.0025)<1e-8);
  assert.equal((await e.undo(cut.legs)).legs.length,0);
});
test('起点A/B仅首way可重设；新选择可单独新段',async () => {
  const e=setup(),a=await e.advance([],{way_id:1});
  let p=await e.startPreview(a.legs,{way_id:1,point:[35,139.0025],replace_current:true});
  assert.equal(p.directions.length,2);
  p=await e.startPreview(a.legs,{way_id:1,point:[35,139.001],replace_current:true});
  assert.equal(p.directions.length,1);
  const b=await e.advance(a.legs,{way_id:2},true);
  await assert.rejects(e.start(b.legs,{way_id:2,point:[35,139.0045],direction:1,replace_current:true}),/首条/);
  const c=await e.start(b.legs,{way_id:8,point:[35,139.0085],direction:0});
  assert.equal(c.legs.length,2);
  assert.equal(c.legs[1].path.length,1);
  const reset=await e.start(c.legs,{way_id:8,point:[35,139.0085],direction:1,replace_current:true});
  assert.equal(reset.legs.length,2);
});
test('结束仅投影当前段与保留区间；未知方向、远点、无变化拒绝',async () => {
  const e=setup(),a=await e.advance([],{way_id:1});
  assert.throws(()=>e.cutPreview(a.legs,{point:[35,139.002]}),/尚未确定/);
  const b=await firstTwo(e);
  assert.throws(()=>e.cutPreview(b.legs,{point:[36,139]}),/150/);
  const c=await e.cut(b.legs,{point:[35,139.004]});
  assert.throws(()=>e.cutPreview(c.legs,{point:[35,139.0045]}),/已经是/);
  const t=await e.advance(b.legs,{way_id:8,transfer:true});
  assert.throws(()=>e.cutPreview(t.legs,{point:[35,139.002]}),/150/);
  const shared=e.cutPreview(b.legs,{point:[35,139.003]}).candidates[0];
  assert.equal(shared.path_index,0);assert.deepEqual(shared.span,[0,2]);
});
test('25米停车点吸附；150米投影限制；缺坐标不跨越连接',async () => {
  const e=setup(undefined,undefined,{},[4]),a=await firstTwo(e);
  const p=e.cutPreview(a.legs,{point:[35,139.0041]}).candidates[0];
  assert.equal(p.snapped,true);assert.deepEqual(p.point,[35,139.004]);
  assert.equal(e.cutPreview(a.legs,{point:[35,139.0045]}).candidates[0].snapped,false);
  await assert.rejects(e.startPreview([],{way_id:1,point:[36,139]}),/150/);
  e.store.coords.delete(2);
  await assert.rejects(e.startPreview([],{way_id:1,point:[35,139.002]}),/完整坐标/);
});
test('星标：端点主线、方向、同名、角度、歧义与缺坐标',() => {
  const ways={10:[1,2],20:[2,3,4],30:[4,5],40:[3,6],50:[4,7]};
  const coords={1:[0,0],2:[0,.001],3:[0,.002],4:[0,.003],5:[0,.004],6:[.0001,.0025],7:[.001,.004]};
  const meta=Object.fromEntries(Object.keys(ways).map(id=>[id,{tags:{name:'线路'}}]));
  meta[40].tags.service='yard';
  const e=setup(ways,coords,meta),path=[{way_id:10},{way_id:20}];
  assert.equal(e.recommend(path,[40,30]),30);
  assert.equal(e.recommend(path,[50,30]),30);
  meta[30].tags.service='yard';
  assert.equal(e.recommend(path,[30,50]),50);
  delete meta[30].tags.service;
  for(const way of e.store.ways.values()) way.nodes.reverse();
  assert.equal(e.recommend(path,[40,30]),30);
  assert.equal(e.recommend([{way_id:20}],[30]),null);
  e.store.ways.get(50).nodes=[...e.nodes(30)];
  assert.equal(e.recommend(path,[30,50]),null);
  e.store.coords.delete(4);
  assert.equal(e.recommend(path,[30]),null);
});
module.exports={setup};
