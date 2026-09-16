// 车站独立图层：仅查询可视范围，缩小时移除，不影响行程或地图视口。
function initStationMap(map) {
  map.createPane('stations');
  map.getPane('stations').style.zIndex = 450;
  const outlines = new Map();
  let request = null;
  let timer = null;
  let revision = 0;
  const Status = L.Control.extend({
    onAdd() {
      const box = L.DomUtil.create('div', 'station-map-status');
      box.setAttribute('role', 'status');
      this.box = box;
      L.DomEvent.disableClickPropagation(box);
      return box;
    }
  });
  const status = new Status({position:'bottomleft'}).addTo(map);
  const message = text => { status.box.textContent = text; status.box.hidden = !text; };
  const clearOutlines = () => {
    outlines.forEach(layer => layer.remove());
    outlines.clear();
  };
  async function update(token) {
    if (map.getZoom() < 14) return;
    const bounds = map.getBounds().pad(0.15);
    const south = Math.max(-90, bounds.getSouth()), north = Math.min(90, bounds.getNorth());
    let west = bounds.getWest(), east = bounds.getEast();
    while (west < -180) { west += 360; east += 360; }
    while (west >= 180) { west -= 360; east -= 360; }
    const ranges = east > 180 ? [[west, 180], [-180, east - 360]] : [[west, east]];
    const controller = new AbortController();
    request = controller;
    try {
      const results = await Promise.all(ranges.map(async ([left, right]) => {
        const params = new URLSearchParams({bbox:[south,left,north,right].join(','), zoom:map.getZoom()});
        const response = await fetch(`/stations/map?${params}`, {signal:controller.signal});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '车站加载失败');
        return data;
      }));
      if (controller.signal.aborted || token !== revision) return;
      const stations = new Map(results.flatMap(result => result.stations).map(station => [station.id, station]));
      outlines.forEach((layer, id) => {
        if (!stations.has(id)) {
          layer.remove();
          outlines.delete(id);
        }
      });
      stations.forEach(station => {
        const polygons = station.polygons.map(polygon => [polygon.map(([lat, lon]) =>
          [lat, lon + 360 * Math.round((map.getCenter().lng - lon) / 360)])]);
        let layer = outlines.get(station.id);
        if (!layer) {
          layer = L.polygon(polygons, {pane:'stations', color:'#7c3aed', weight:2,
            fillColor:'#7c3aed', fillOpacity:0.04}).addTo(map);
          outlines.set(station.id, layer);
          const label = document.createElement('span');
          label.textContent = station.outline_kind === '车站建筑' ? station.name : `${station.name} · ${station.outline_kind}`;
          layer.bindTooltip(label, {permanent:false, sticky:true, direction:'top', className:'station-map-label'});
          layer.on('mouseover', () => layer.setStyle({weight:3, fillOpacity:0.15}));
          layer.on('mouseout', () => layer.setStyle({weight:2, fillOpacity:0.04}));
        } else layer.setLatLngs(polygons);
      });
      message(results.some(result => result.truncated) ? '车站较多，请放大地图查看完整结果。' : '');
    } catch (error) {
      if (!controller.signal.aborted && token === revision) message(`${error.message}，移动地图后重试。`);
    }
  }
  function schedule() {
    revision++;
    request?.abort();
    clearTimeout(timer);
    if (map.getZoom() < 14) {
      clearOutlines();
      message('放大地图可查看车站轮廓');
      return;
    }
    // 等待拖动/缩放结束，快速连续操作时取消旧请求，防止过期结果覆盖新视野。
    const token = revision;
    timer = setTimeout(() => update(token), 250);
  }
  map.on('moveend zoomend', schedule);
  schedule();
}
