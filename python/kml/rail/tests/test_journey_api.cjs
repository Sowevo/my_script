const {test} = require('node:test'), assert = require('node:assert/strict');
global.JourneyEngine = require('../app/static/journey_engine.js').JourneyEngine;
const {createJourneyApi,startRestriction} = require('../app/static/journey_api.js');
const ways={1:[1,2],2:[2,3],3:[3,4],9:[9,10]};
let version='china',requests=[],failId=null,waitTrack=null;
global.fetch=async(url,options={})=>{
  const body=options.body ? JSON.parse(options.body) : {};
  requests.push({url,body,options});
  if(url==='/diagnostics')return {ok:true,json:async()=>({ok:true})};
  if(url.startsWith('/dataset'))return {ok:true,json:async()=>({dataset_version:version})};
  if(body.dataset_version!==version)return {ok:false,json:async()=>({code:'dataset_changed',dataset_version:version})};
  if(waitTrack)await waitTrack;
  if(body.way_ids.includes(failId))throw new Error('模拟网络失败');
  const nodes=[...new Set(body.way_ids.flatMap(id=>ways[id]))];
  return {ok:true,json:async()=>({dataset_version:version,
    ways:Object.fromEntries(body.way_ids.map(id=>[id,{nodes:ways[id],meta:{tags:{name:'测试'}}}])),
    coords:Object.fromEntries(nodes.map(n=>[n,[35,139+n*.001]])),
    node_ways:Object.fromEntries(nodes.map(n=>[n,Object.entries(ways).filter(([id,ns])=>ns.includes(n)).map(([id])=>+id)])),
    stops:[]})};
};
function page(){
  let data=null,message='';
  const api=createJourneyApi({getData:()=>data,datasetVersion:version,onDatasetChanged:m=>message=m});
  return {api,get data(){return data},set data(d){data=d},get message(){return message}};
}
test('数据按需加载复用；请求不含行程、坐标或Cookie；两页面独立',async()=>{
  requests=[];const p=page(),q=page();
  p.data=await p.api.advance({way_id:1});
  assert.equal(p.data.legs[0].path.length,1);assert.equal(q.data,null);
  const reads=requests.filter(r=>r.url==='/track-data').length;
  await p.api.startPreview({way_id:1,point:[35,139.0015],replace_current:true});
  assert.equal(requests.filter(r=>r.url==='/track-data').length,reads);
  p.data=await p.api.advance({way_id:2});
  assert.equal(p.data.legs[0].path.length,3);
  for(const request of requests){
    assert.equal(request.options.credentials,'omit');
    assert.ok(!('legs' in request.body));
    assert.ok(!('path' in request.body));
    assert.ok(!('coords' in request.body));
    assert.ok(!request.url.startsWith('/journey'));
  }
  assert.equal(page().data,null,'新页面没有恢复');
  assert.match(startRestriction(p.data,null),/首条/);
  assert.equal(startRestriction(p.data,9),'');
});
test('后端切换：内存已有数据的操作也拒绝；原行程保留供导出；清空重新绑定',async()=>{
  const p=page();p.data=await p.api.advance({way_id:1});const before=p.data;
  version='japan';
  await assert.rejects(p.api.undo(),/数据源已切换/);
  assert.equal(p.data,before);assert.ok(p.data.total_path_coords.length);
  assert.equal(p.api.blocked,true);assert.match(p.message,/导出/);
  p.data=await p.api.clear();
  assert.equal(p.data.legs.length,0);
  p.data=await p.api.advance({way_id:9});
  assert.equal(p.data.dataset_version,'japan');
  assert.equal(p.api.blocked,false);
});
test('失败的自动推进草稿不覆盖已显示行程',async()=>{
  const p=page();p.data=await p.api.advance({way_id:1});const before=p.data;
  failId=3;
  await assert.rejects(p.api.advance({way_id:2}),/模拟网络失败/);
  assert.equal(p.data,before);assert.equal(p.data.legs[0].path.length,1);
  failId=null;
});
test('重复修改拒绝；预览和版本过期结果丢弃',async()=>{
  const p=page();
  let release;waitTrack=new Promise(resolve=>release=resolve);
  const pending=p.api.advance({way_id:1});
  await assert.rejects(p.api.advance({way_id:1}),/上一项操作/);
  release();waitTrack=null;p.data=await pending;
  await assert.rejects(p.api.start({way_id:1,revision:-1,point:[35,139.0015],direction:1}),/行程已变化/);
  // 当前预览在加载另一条way时清空；晚返回不能改变数据版本或提交结果。
  let resume;waitTrack=new Promise(resolve=>resume=resolve);
  const preview=p.api.startPreview({way_id:9,point:[35,139.0095]});
  await new Promise(resolve=>setImmediate(resolve));
  p.data=await p.api.clear();
  resume();waitTrack=null;
  await assert.rejects(preview,/过期/);
  assert.equal(p.data.legs.length,0);assert.equal(p.api.blocked,false);
});
