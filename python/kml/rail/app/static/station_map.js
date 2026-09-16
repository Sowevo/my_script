// 车站独立图层：仅查询可视范围，缩小时移除，不影响行程或地图视口。
function stationTooltip(station) {
  const label = document.createElement('div');
  const title = document.createElement('strong');
  title.textContent = station.name;
  label.appendChild(title);
  const lines = station.lines || [];
  if (!lines.length) return label;
  lines.slice(0, 3).forEach(line => {
    const row = document.createElement('div');
    const prefix = line.operator && !line.name.includes(line.operator) ? `${line.operator} · ` : '';
    row.textContent = prefix + line.name;
    label.appendChild(row);
  });
  if (lines.length > 3) {
    const more = document.createElement('div');
    more.textContent = `另有 ${lines.length - 3} 条线路`;
    label.appendChild(more);
  }
  return label;
}

function stationIcon() {
  const glyph = document.createElement('i');
  glyph.className = 'bi bi-train-front-fill';
  glyph.setAttribute('aria-hidden', 'true');
  return L.divIcon({className:'station-map-icon', html:glyph,
    iconSize:[22,22], iconAnchor:[11,11], tooltipAnchor:[10,0]});
}

function initStationMap(map) {
  map.createPane('stations');
  map.getPane('stations').style.zIndex = 450;
  const markers = new Map();
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
  const clearMarkers = () => {
    markers.forEach(layer => layer.remove());
    markers.clear();
  };
  function renderStations(stations) {
    markers.forEach((layer, id) => {
      if (!stations.has(id)) {
        layer.remove();
        markers.delete(id);
      }
    });
    stations.forEach((station, id) => {
      const point = [station.lat, station.lon + 360 * Math.round((map.getCenter().lng - station.lon) / 360)];
      let layer = markers.get(id);
      if (!layer) {
        layer = L.marker(point, {pane:'stations', icon:stationIcon(), alt:station.name, riseOnHover:true}).addTo(map);
        layer.getElement().setAttribute('aria-label', station.name);
        layer.bindTooltip(stationTooltip(station),
          {permanent:false, direction:'auto', className:'station-map-detail'});
        markers.set(id, layer);
      } else layer.setLatLng(point);
    });
  }
  async function update(token) {
    if (map.getZoom() < 16) return;
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
        if (!response.ok) {
          const error = new Error(data.error || '车站加载失败');
          error.hasServerMessage = Boolean(data.error);
          throw error;
        }
        return data;
      }));
      if (controller.signal.aborted || token !== revision) return;
      renderStations(new Map(results.flatMap(result => result.stations).map(station => [station.id, station])));
      message(results.some(result => result.truncated) ? '车站较多，请放大地图查看完整结果。' : '');
    } catch (error) {
      if (!controller.signal.aborted && token === revision) {
        // 服务端提示直接显示，缺少索引等问题不能通过移动地图解决。
        message(error.hasServerMessage ? error.message : '车站加载失败，请移动地图后重试。');
      }
    }
  }
  function schedule() {
    revision++;
    request?.abort();
    clearTimeout(timer);
    if (map.getZoom() < 16) {
      clearMarkers();
      message('放大地图可查看车站');
      return;
    }
    // 等待拖动/缩放结束，快速连续操作时取消旧请求，防止过期结果覆盖新视野。
    const token = revision;
    timer = setTimeout(() => update(token), 250);
  }
  map.on('moveend zoomend resize', schedule);
  schedule();
}
