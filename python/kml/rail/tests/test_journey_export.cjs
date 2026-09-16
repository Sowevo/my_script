const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
vm.runInThisContext(fs.readFileSync(__dirname + '/../app/static/journey_export.js', 'utf8'));
const data = {
  legs: [{name:'单轨 & <线路>'}, {name:'JR', transfer_label:'滨松町'}],
  total_path_coords: [
    {leg:0, coords:[[35,139],[36,140]]},
    {leg:0, coords:[[37,141],[36,140]]},
    {leg:1, coords:[[38,142],[39,143]]},
  ],
};
assert.deepEqual(journeyLines(data.total_path_coords.slice(0,2)), [[[35,139],[36,140],[37,141]]]);
assert.equal(journeyLines([{coords:[[0,0],[1,1]]},{coords:[[5,5],[6,6]]}]).length, 2);
assert.equal(journeyLines([{coords:[[0,0],[1,1],[2,2]]},{coords:[[1,1],[3,3]]}]).length, 2);
const kml = journeyKml(data, 'all', ['#003685','#1976d2']);
assert.equal((kml.match(/<Placemark>/g)||[]).length, 2);
assert.equal((kml.match(/<LineString>/g)||[]).length, 2);
assert.ok(kml.includes('ff853600'));
assert.ok(kml.includes('单轨 &amp; &lt;线路&gt;'));
assert.ok(kml.includes('139,35,0 140,36,0 141,37,0'));
assert.ok(!kml.includes('141,37,0 142,38,0'));
assert.equal((journeyKml(data, '1', ['#003685','#1976d2']).match(/<Placemark>/g)||[]).length, 1);
assert.deepEqual(data.total_path_coords[1].coords, [[37,141],[36,140]]);
console.log('KML 分段、端点拼接、缺口、颜色、XML 转义、单段导出检查通过');

assert.deepEqual(journeyEndpoints(data, 'all'), [[35,139],[39,143]]);
assert.deepEqual(journeyEndpoints(data, '1'), [[38,142],[39,143]]);
assert.equal(journeyEndpoints({legs:[],total_path_coords:[]}, 'all'), null);
assert.equal(stationFilename(' 羽田空港 ', '高田馬場'), '羽田空港 → 高田馬場.kml');
assert.ok(!stationFilename('A/B', 'C:D').includes('/'));
assert.ok(journeyKml(data, 'all', ['#003685','#1976d2'], 'A & B → C').includes('<name>A &amp; B → C</name>'));
console.log('导出端点、站名文件名和文档名检查通过');

const transferData = {...data, legs:[{path:[{way_id:10},{way_id:11}]},{path:[{way_id:20}]}]};
assert.deepEqual(stationEndpoints(transferData, 'all'), [
  {point:[35,139],way_ids:[10,11]}, {point:[37,141],way_ids:[11,10]},
  {point:[38,142],way_ids:[20]}, {point:[39,143],way_ids:[20]},
]);
assert.equal(stationEndpoints(transferData, '1').length, 2);
assert.equal(stationFilename('A', 'B', 'C'), 'A → B → C.kml');
console.log('多段端点、单段范围与途经站命名检查通过');
const grouped = groupedStationNames([
  {name:'A',group:'start'}, {name:'B1',group:'t1'}, {name:'B2',group:'t1'},
  {name:'C',group:'t2'}, {name:'D',group:'end'},
]);
assert.deepEqual(grouped, ['A', 'B1（B2）', 'C', 'D']);
assert.equal(stationFilename(...grouped), 'A → B1（B2） → C → D.kml');
assert.deepEqual(groupedStationNames([{name:'A',group:'start'},{name:'B',group:'t1'},{name:'C',group:'end'}]), ['A','B','C']);
console.log('换乘双站名括号格式及删除、合并后分组检查通过');

const cutData = {legs:[{name:'截断线路',path:[{way_id:1,span:[0,0.5]}]}],
  total_path_coords:[{leg:0,id:1,coords:[[35,139],[35,139.0005]]}]};
assert.deepEqual(stationEndpoints(cutData,'all')[1].point,[35,139.0005]);
const cutKml=journeyKml(cutData,'all',['#1976d2']);
assert.ok(cutKml.includes('139,35,0 139.0005,35,0'));
assert.ok(!cutKml.includes('139.001,35,0'));
cutData.total_path_coords.push({leg:0,id:1,coords:[[35,139.0005],[35,139.001]]});
assert.deepEqual(journeyLines(cutData.total_path_coords),[[[35,139],[35,139.0005],[35,139.001]]]);
console.log('截断坐标、导出终点及同 way 剩余部分拼接检查通过');
