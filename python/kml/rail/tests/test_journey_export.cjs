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
