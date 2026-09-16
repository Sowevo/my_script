const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {}, active = new Set(), requests = [];
let zoom = 13;
const element = () => ({children:[],setAttribute(){},appendChild(child){this.children.push(child);},textContent:'',hidden:false});
const map = {
  createPane(){},getPane:()=>({style:{}}),getZoom:()=>zoom,getCenter:()=>({lng:139}),
  getBounds:()=>({pad(){return this;},getSouth:()=>35,getNorth:()=>35.01,getWest:()=>139,getEast:()=>139.01}),
  on(events,fn){events.split(' ').forEach(event=>(listeners[event] ||= []).push(fn));},
};
const L = {
  Control:{extend(methods){return class {addTo(){methods.onAdd.call(this);return this;}};}},
  DomUtil:{create:element},DomEvent:{disableClickPropagation(){}},
  layerGroup:()=>({addTo(){return this;},clearLayers(){}}),
  polygon:()=>({addTo(){active.add(this);return this;},remove(){active.delete(this);},
    on(){},setLatLngs(){},setStyle(){},bindTooltip(label, options){assert.equal(options.permanent,false);assert.equal(options.sticky,true);}}),
};
const context={L,document:{createElement:element},setTimeout,clearTimeout,AbortController,URLSearchParams,
  fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/station_map.js','utf8'),context);
const tooltip = context.stationTooltip({name:'浜松町'}, {scope:'station',lines:
  ['山手線','京浜東北線','第三线','第四线'].map(name=>({name,operator:'JR'}))});
assert.equal(tooltip.children[0].textContent,'浜松町');
assert.equal(tooltip.children[1].textContent,'本站线路：JR · 山手線、京浜東北線、第三线，另有 1 条线路');
assert.equal(context.stationTooltip({name:'未知站'}, {}).children.length,1);
assert.equal(context.stationTooltip({name:'单轨'}, {scope:'platform',lines:[{name:'東京モノレール羽田空港線',operator:'東京モノレール'}]}).children[1].textContent,'東京モノレール羽田空港線');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const station=id=>({id,name:id,polygons:[[[35,139],[35,139.001],[35.001,139],[35,139]]]});
(async()=>{
  context.initStationMap(map);
  await pause(280); assert.equal(requests.length,0);
  zoom=15;
  for(let i=0;i<4;i++) listeners.moveend.forEach(fn=>fn());
  await pause(280); assert.equal(requests.length,1);
  requests[0].resolve({ok:true,json:async()=>({stations:[station('relation/1'),station('relation/2')],truncated:false})});
  await pause(0); assert.equal(active.size,2);
  listeners.moveend.forEach(fn=>fn());
  await pause(280);
  requests[1].resolve({ok:true,json:async()=>({stations:[station('relation/2')],truncated:false})});
  await pause(0); assert.equal(active.size,1);
  listeners.moveend.forEach(fn=>fn());
  await pause(280);
  zoom=13;listeners.zoomend.forEach(fn=>fn());
  assert.equal(active.size,0);assert.equal(requests[2].options.signal.aborted,true);
  requests[2].resolve({ok:true,json:async()=>({stations:[station('relation/3')],truncated:false})});
  await pause(0); assert.equal(active.size,0);
  console.log('建筑轮廓、悬浮名称、缩放阈值、防抖及过期响应检查通过');
})().catch(error=>{console.error(error);process.exitCode=1;});
