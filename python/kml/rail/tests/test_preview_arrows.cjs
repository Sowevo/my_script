const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const layers = new Set(), handlers = new Map();
const drawnColours = [];
const context = {L:{
  layerGroup:() => ({items:[],addTo(){layers.add(this);return this;},clearLayers(){this.items=[];}}),
  polyline:(coords,style) => ({addTo(layer){layer.items.push(coords);drawnColours.push(style.color);}})
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/track_styles.js','utf8'),context);
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/preview_arrows.js','utf8'),context);
const map = {removeLayer:layer=>layers.delete(layer),getBounds:()=>({contains:()=>true}),
  latLngToLayerPoint:([x,y])=>({x,y}),layerPointToLatLng:p=>p,
  on:(event,fn)=>handlers.set(event,fn),off:event=>handlers.delete(event)};
const arrows = context.initPreviewArrows(map);
// 各调用场景都使用相同的入口；反序截断不能改变 OSM 运行方向。
for (const key of ['nearby','start','choices','choice-highlight','journey']) {
  for (const reversed of [false,true]) {
    for (const oneway of ['yes','-1']) {
      const coords = reversed ? [[200,0],[0,0]] : [[0,0],[200,0]];
      arrows.showTracks(key,[{coords,reversed,meta:{tags:{oneway}}}]);
      const line = [...layers].at(-1).items[0];
      assert.equal(line[1][0] > line[0][0],oneway==='yes');
      arrows.clear(key);
    }
  }
}
// 同一关系的成员标签不同，分别绘制；无方向数据不画。
arrows.showTracks('nearby',[
  {coords:[[0,0],[200,0]],tags:{oneway:'yes'}},
  {coords:[[0,1],[200,1]],tags:{oneway:'-1'}},
  {coords:[[0,2],[200,2]],tags:{}}
]);
assert.equal([...layers][0].items.length,4);
handlers.get('zoomend moveend')();
assert.equal([...layers][0].items.length,4);
arrows.showTracks('nearby',[]);
assert.equal(layers.size,1);
assert.equal([...layers][0].items.length,0);
arrows.destroy();
assert.equal(layers.size,0);
assert.equal(handlers.size,0);
const colourArrows=context.initPreviewArrows(map);
drawnColours.length=0;
colourArrows.showTracks('journey',[
  {coords:[[0,0],[200,0]],tags:{oneway:'yes'},color:'#00aaff'},
  {coords:[[0,1],[200,1]],tags:{oneway:'yes'},color:'#ee9900'}
]);
assert.deepEqual(drawnColours,['#00aaff','#00aaff','#ee9900','#ee9900']);
drawnColours.length=0;
colourArrows.showTracks('highlight',[{coords:[[0,0],[200,0]],tags:{oneway:'yes'}}],{color:'red'});
assert.deepEqual(drawnColours,['red','red']);
colourArrows.destroy();
const disabled=context.initPreviewArrows(map,{enabled:false});
disabled.showTracks('journey',[{coords:[[0,0],[200,0]],tags:{oneway:'yes'}}]);
assert.equal(layers.size,0);
disabled.destroy();
console.log('统一方向规则、反序截断、混合关系、图层清理与开关检查通过');
