const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
let calls=[],changed=null,message='',ok=true,revision='current';
const context={AbortController,fetch:async(url,options)=>{
  calls.push({url,body:JSON.parse(options.body)});
  return {ok,json:async()=>ok?{legs:[{}],revision}:{error:'尚未确定行进方向'}};
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/journey_cut.js','utf8'),context);
// 不提供任何地图/弹窗 API，确保结束操作不会弹窗或移动视口。
const control=context.initJourneyCut({},{
  getData:()=>({revision:'current'}),runAction:fn=>fn(),
  onChanged:data=>{changed=data;},status:text=>{message=text;}
});
(async()=>{
  await control.open({lat:35,lng:139});
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'/journey/cut');
  assert.equal(calls[0].body.revision,'current');
  assert.equal(changed.legs.length,1);assert.match(message,/退回一步/);
  changed=null;ok=false;
  await assert.rejects(control.open({lat:35,lng:139}),/尚未确定行进方向/);
  assert.equal(changed,null);
  const unavailable=await control.check({lat:35,lng:139});
  assert.equal(unavailable.allowed,false);assert.match(unavailable.reason,/方向/);
  ok=true;
  assert.equal((await control.check({lat:35,lng:139})).allowed,true);
  assert.equal(changed,null);
  revision='stale';
  assert.equal((await control.check({lat:35,lng:139})).allowed,false);
  assert.equal(calls.at(-1).url,'/journey/cut-preview');
  console.log('单请求直接结束、错误不改行程、无弹窗和视口操作检查通过');
})().catch(error=>{console.error(error);process.exitCode=1;});
