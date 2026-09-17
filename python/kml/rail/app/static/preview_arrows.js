// 所有轨道图层共用 OSM 方向箭头；关闭 enabled 即可停用。
function initPreviewArrows(map, {enabled = true} = {}) {
  const previews = new Map();
  function clear(key) {
    const preview = previews.get(key);
    if (preview) map.removeLayer(preview.layer);
    previews.delete(key);
  }
  function draw(preview) {
    preview.layer.clearLayers();
    const bounds = map.getBounds();
    let count = 0;
    for (const {coords:line, color} of preview.lines) {
      let remaining = 45;
      for (let i = 1; i < line.length; i++) {
        const a = map.latLngToLayerPoint(line[i - 1]);
        const b = map.latLngToLayerPoint(line[i]);
        const length = Math.hypot(b.x - a.x, b.y - a.y);
        if (!length) continue;
        const dx = (b.x - a.x) / length, dy = (b.y - a.y) / length;
        for (; remaining <= length; remaining += 90) {
          const x = a.x + dx * remaining, y = a.y + dy * remaining;
          const tip = map.layerPointToLatLng([x, y]);
          if (!bounds.contains(tip)) continue;
          const left = map.layerPointToLatLng([x - dx * 10 - dy * 5, y - dy * 10 + dx * 5]);
          const right = map.layerPointToLatLng([x - dx * 10 + dy * 5, y - dy * 10 - dx * 5]);
          L.polyline([left, tip, right], {...TRACK_STYLES.arrow, color}).addTo(preview.layer);
          if (++count >= 100) return;
        }
        remaining -= length;
      }
    }
  }
  function show(key, lines) {
    clear(key);
    if (!enabled) return;
    const preview = {lines, layer:L.layerGroup().addTo(map)};
    previews.set(key, preview);
    draw(preview);
  }
  const redraw = () => previews.forEach(draw);
  map.on('zoomend moveend', redraw);
  function showTracks(key, tracks, style = TRACK_STYLES.preview) {
    show(key, tracks.flatMap(track => railPreviewLines(
      track.meta?.tags || track.tags || {}, [track.coords], Boolean(track.reversed))
      .map(coords => ({coords, color:track.color || style.color}))));
  }
  return {showTracks, clear, destroy() {
    [...previews.keys()].forEach(clear);
    map.off('zoomend moveend', redraw);
  }};
}

// 首选方向不等同于单行限制；无明确依据时不使用节点顺序猜测。
function railPreviewDirection(tags = {}) {
  if (['yes', '1', 'true'].includes(tags.oneway)) return {reverse:false, label:'单行方向'};
  if (tags.oneway === '-1') return {reverse:true, label:'单行方向'};
  const preferred = tags['railway:preferred_direction'];
  if (preferred === 'forward' || preferred === 'backward') {
    return {reverse:preferred === 'backward', label:'首选运行方向（非单行限制）'};
  }
  return null;
}

// 截断后的几何可能逆节点顺序，先还原，再按 OSM 方向排列。
function railPreviewLines(tags, lines, reversed = false) {
  const direction = railPreviewDirection(tags);
  if (!direction) return [];
  return lines.map(coords => direction.reverse !== reversed ? [...coords].reverse() : coords);
}
