// 车站独立图层：仅查询可视范围，缩小时移除，不影响行程或地图视口。
function stationTooltip(station, info) {
  const label = document.createElement('div');
  const title = document.createElement('strong');
  title.textContent = station.name;
  label.appendChild(title);
  const lines = info?.lines || [];
  if (!lines.length) return label;
  const detail = document.createElement('div');
  const shown = lines.slice(0, 3);
  const operators = [...new Set(shown.map(line => line.operator).filter(Boolean))];
  const operator = operators.length === 1 && shown.every(line => line.operator === operators[0])
    ? operators[0] : '';
  const names = shown.map(line => {
    const prefix = !operator && line.operator && !line.name.includes(line.operator)
      ? `${line.operator} · ` : '';
    return prefix + line.name;
  });
  const prefix = operator && !shown.every(line => line.name.includes(operator)) ? `${operator} · ` : '';
  detail.textContent = (info.scope === 'station' ? '本站线路：' : '') + prefix + names.join('、')
    + (lines.length > 3 ? `，另有 ${lines.length - 3} 条线路` : '');
  label.appendChild(detail);
  return label;
}

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
      // 每个站台独立绑定提示，避免把同站所有线路误标到某一站台。
      const stations = new Map(results.flatMap(result => result.stations).flatMap(station =>
        station.polygons.map((polygon, index) => [`${station.id}/${index}`,
          {...station, polygons:[polygon], info:station.polygon_labels?.[index]}])));
      outlines.forEach((layer, id) => {
        if (!stations.has(id)) {
          layer.remove();
          outlines.delete(id);
        }
      });
      stations.forEach((station, id) => {
        const polygons = station.polygons.map(polygon => [polygon.map(([lat, lon]) =>
          [lat, lon + 360 * Math.round((map.getCenter().lng - lon) / 360)])]);
        let layer = outlines.get(id);
        if (!layer) {
          layer = L.polygon(polygons, {pane:'stations', color:'#7c3aed', weight:2,
            fillColor:'#7c3aed', fillOpacity:0.04}).addTo(map);
          outlines.set(id, layer);
          layer.on('mouseover', () => layer.setStyle({weight:3, fillOpacity:0.15}));
          layer.on('mouseout', () => layer.setStyle({weight:2, fillOpacity:0.04}));
        } else layer.setLatLngs(polygons);
        layer.bindTooltip(stationTooltip(station, station.info),
          {permanent:false, sticky:true, direction:'top', className:'station-map-label'});
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
