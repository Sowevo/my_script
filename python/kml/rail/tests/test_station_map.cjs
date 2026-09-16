const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {}, active = new Set(), requests = [], markerPoints = [];
let zoom = 15;
const element = () => ({children:[],setAttribute(){},appendChild(child){this.children.push(child);},textContent:'',hidden:false});
const map = {
  createPane(){},getPane:()=>({style:{}}),getZoom:()=>zoom,getCenter:()=>({lng:139}),
  getBounds:()=>({pad(){return this;},getSouth:()=>35,getNorth:()=>35.01,getWest:()=>139,getEast:()=>139.01}),
  on(events,fn){events.split(' ').forEach(event=>(listeners[event] ||= []).push(fn));},
};
const L = {
  Control:{extend(methods){return class {addTo(){methods.onAdd.call(this);return this;}};}},
  DomUtil:{create:element},DomEvent:{disableClickPropagation(){}},
  divIcon:options=>{assert.equal(options.html.className,'bi bi-train-front-fill');return options;},
  marker:point=>(markerPoints.push(point), {
    getElement:element,addTo(){active.add(this);return this;},remove(){active.delete(this);},setLatLng(){},
    bindTooltip(label, config){assert.equal(config.permanent,false);assert.equal(config.className,'station-map-detail');this.label=label;return this;},
    bindPopup(){throw new Error("车站仅保留悬浮提示，不应绑定点击弹窗");}
  }),
};
const context={L,document:{createElement:element},setTimeout,clearTimeout,AbortController,URLSearchParams,
  fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/station_map.js','utf8'),context);
const tooltip = context.stationTooltip({name:'浜松町',lines:
  ['山手線','京浜東北線','第三线','第四线'].map(name=>({name,operator:'JR'}))});
assert.equal(tooltip.children[0].textContent,'浜松町');
assert.equal(tooltip.children.length,5);
assert.equal(tooltip.children[1].textContent,'JR · 山手線');
assert.equal(tooltip.children[2].textContent,'JR · 京浜東北線');
assert.equal(tooltip.children[3].textContent,'JR · 第三线');
assert.equal(tooltip.children[4].textContent,'另有 1 条线路');
assert.equal(context.stationTooltip({name:'未知站'}).children.length,1);
assert.equal(context.stationIcon().html.className,'bi bi-train-front-fill');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const station=id=>({id,name:"東京",lat:35,lon:139,lines:[]});
(async()=>{
  context.initStationMap(map);
  await pause(280); assert.equal(requests.length,0);
  zoom=16;
  for(let i=0;i<4;i++) listeners.moveend.forEach(fn=>fn());
  await pause(280); assert.equal(requests.length,1);
  requests[0].resolve({ok:true,json:async()=>({stations:[station('relation/1'),station('relation/2')],truncated:false})});
  await pause(0); assert.equal(active.size,2);
  assert.equal(markerPoints[0][0],35);
  listeners.moveend.forEach(fn=>fn());
  await pause(280);
  requests[1].resolve({ok:true,json:async()=>({stations:[station('relation/2')],truncated:false})});
  await pause(0); assert.equal(active.size,1);
  listeners.moveend.forEach(fn=>fn());
  await pause(280);
  zoom=15;listeners.zoomend.forEach(fn=>fn());
  assert.equal(active.size,0);assert.equal(requests[2].options.signal.aborted,true);
  requests[2].resolve({ok:true,json:async()=>({stations:[station('relation/3')],truncated:false})});
  await pause(0); assert.equal(active.size,0);
  console.log('车站图标、悬浮名称、缩放阈值、防抖及过期响应检查通过');
})().catch(error=>{console.error(error);process.exitCode=1;});
