const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const requests=[],active=new Set(),events={};
let changed=null, fits=0;
let arrowLines=null;
const previewArrows={showTracks(key,tracks){arrowLines=tracks.flatMap(track=>context.railPreviewLines(track.tags,[track.coords]));},clear(){arrowLines=null;}};
const el=()=>({children:[],style:{},hidden:true,appendChild(child){this.children.push(child);},replaceChildren(){this.children=[];},setAttribute(){}});
const panel=el(),list=el();
const map={on(name,fn){events[name]=fn;},removeLayer(layer){active.delete(layer);},fitBounds(){fits++;}};
const layer=()=>({events:{},addTo(){active.add(this);return this;},on(name,fn){this.events[name]=fn;return this;},
  bindTooltip(){return this;},getBounds(){return [];},setStyle(){}});
const preview={revision:'r1',point:[35,139.5],snapped:false,directions:[
  {id:0,span:[.5,0],coords:[[35,139.5],[35,139]]},
  {id:1,span:[.5,1],coords:[[35,139.5],[35,140]]}]};
const context={document:{createElement:el},L:{polyline:layer,circleMarker:layer,DomEvent:{stopPropagation(){}}},
  fetch:async(url,options)=>{
    requests.push({url,body:options?JSON.parse(options.body):null});
    return {ok:true,json:async()=>url.startsWith('/elements')?{tags:{name:'西武新宿線',oneway:'yes'},geometry:[[[35,139],[35,140]]]}:
      url.endsWith('preview')?preview:{legs:[{path:[{way_id:1,span:[.5,1]}]}]}};
  }};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/../app/static/journey_start.js','utf8'),context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/track_styles.js','utf8'),context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/preview_arrows.js','utf8'),context);
const controller=context.initJourneyStart(map,{panel,list,previewArrows,restoreList(){list.hidden=true;},busy:()=>false,hasJourney:()=>false,
  api:{
    read:async url=>(await context.fetch(url)).json(),
    startPreview:async body=>(await context.fetch('/journey/start-preview',{body:JSON.stringify(body)})).json(),
    start:async body=>(await context.fetch('/journey/start',{body:JSON.stringify(body)})).json()
  },clearReference(){},runAction:fn=>fn(),onChanged:data=>{changed=data;}});
(async()=>{
  await controller.select(1,{lat:35,lng:139.5});
  assert.equal(JSON.stringify(arrowLines),'[[[35,139],[35,140]]]');
  assert.equal(requests.length,2);assert.deepEqual(requests.at(-1).body.point,[35,139.5]);assert.equal(changed,null);assert.equal(controller.active,true);
  await controller.choosePoint({lat:35,lng:139.5});
  assert.equal(requests.at(-1).url,'/journey/start-preview');assert.equal(changed,null);
  controller.cancel();assert.equal(active.size,0);assert.equal(requests.length,3);
  await controller.select(1,{lat:35,lng:139.5});await controller.choosePoint({lat:35,lng:139.5});
  const before=fits;
  const wholeWayArrows=arrowLines;
  const rows=list.children[1].children;
  assert.equal(rows[0].children[0].textContent,'1-A（西武新宿線）');
  assert.equal(rows[1].children[0].textContent,'1-B（西武新宿線）');
  rows[0].children[0].onmouseenter();assert.equal(fits,before);
  rows[0].children[0].onmouseleave();
  assert.equal(JSON.stringify(arrowLines),JSON.stringify(wholeWayArrows));
  rows[1].children[0].onmouseenter();
  rows[1].children[0].onmouseleave();
  assert.equal(JSON.stringify(arrowLines),JSON.stringify(wholeWayArrows));
  await rows[1].children[0].onclick();
  assert.equal(requests.at(-1).url,'/journey/start');assert.equal(requests.at(-1).body.direction,1);
  assert.equal(requests.at(-1).body.reset,true);assert.equal(fits,before);
  assert.equal(controller.active,false);assert.equal(active.size,0);
  assert.equal(arrowLines,null);
  assert.deepEqual(changed.legs[0].path[0].span,[.5,1]);
  assert.equal(requests.filter(r=>r.url==='/journey/start').length,1);
  assert.ok(!requests.some(r=>r.url.startsWith('/ways/')));
  console.log('选轨道/选点不写行程、A/B 方向提交、取消清理及不自动推进检查通过');
})().catch(error=>{console.error(error);process.exitCode=1;});
