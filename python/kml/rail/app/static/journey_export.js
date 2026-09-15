// 地图与 KML 共用每段行程的颜色，非法 OSM 色值回退到默认色。
function journeyColour(leg, index = 0) {
  const palette = ['#1976d2', '#8e44ad', '#00897b', '#e67e22', '#c0392b'];
  const context = document.createElement('canvas').getContext('2d');
  for (const value of leg.colour_candidates || []) {
    if (typeof value !== 'string' || !CSS.supports('color', value) ||
        /^(inherit|initial|unset|revert|currentcolor)$/i.test(value.trim()) || value.includes('(')) continue;
    context.fillStyle = '#1976d2';
    context.fillStyle = value.trim();
    if (/^#[0-9a-f]{6}$/i.test(context.fillStyle)) return context.fillStyle;
  }
  return palette[index % palette.length];
}

// 只拼接端点相同的轨道；分叉、缺口以及换乘段始终保持独立。
function journeyLines(items) {
  const lines = [];
  const same = (a, b) => a[0] === b[0] && a[1] === b[1];
  for (const item of items) {
    if (item.coords.length < 2) continue;
    let points = item.coords.map(point => [...point]);
    const previous = lines[lines.length - 1];
    if (previous) {
      if (!same(previous.at(-1), points[0]) && !same(previous.at(-1), points.at(-1)) &&
          (same(previous[0], points[0]) || same(previous[0], points.at(-1)))) previous.reverse();
      if (same(previous.at(-1), points.at(-1))) points.reverse();
      if (same(previous.at(-1), points[0])) {
        previous.push(...points.slice(1));
        continue;
      }
    }
    lines.push(points);
  }
  return lines;
}

function journeyKml(data, scope, colours) {
  const escapeXml = value => String(value).replace(/[<>&"']/g, c => ({
    '<':'&lt;', '>':'&gt;', '&':'&amp;', '"':'&quot;', "'":'&apos;'
  })[c]);
  const placemarks = data.legs.flatMap((leg, index) => {
    if (scope !== 'all' && Number(scope) !== index) return [];
    const lines = journeyLines(data.total_path_coords.filter(item => item.leg === index));
    const hex = colours[index].slice(1);
    const colour = 'ff' + hex.slice(4, 6) + hex.slice(2, 4) + hex.slice(0, 2);
    const geometry = lines.map(points => '<LineString><tessellate>1</tessellate><coordinates>' +
      points.map(([lat, lon]) => `${lon},${lat},0`).join(' ') + '</coordinates></LineString>').join('');
    return [`<Placemark><name>${escapeXml(`第 ${index + 1} 段 · ${leg.name}`)}</name>` +
      `<description>${escapeXml(leg.transfer_label || '')}</description>` +
      `<Style><LineStyle><color>${colour}</color><width>4</width></LineStyle></Style>` +
      `<MultiGeometry>${geometry}</MultiGeometry></Placemark>`];
  });
  return '<?xml version="1.0" encoding="UTF-8"?>' +
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>轨道行程</name>' +
    placemarks.join('') + '</Document></kml>';
}

// 用线路名和导出范围命名，保留中文并清理文件名禁用字符。
function journeyFilename(data, scope) {
  const clean = value => Array.from(String(value || '未命名轨道')
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, ' ')
    .replace(/\s+/g, ' ').trim() || '未命名轨道').slice(0, 16).join('');
  let title;
  if (scope === 'all') {
    const names = [...new Set(data.legs.map(leg => leg.name || '未命名轨道'))];
    title = names.slice(0, 3).map(clean).join('、');
    if (names.length > 3) title += `等${names.length}条线路`;
    title += '_全部行程';
  } else {
    const index = Number(scope);
    title = `${clean(data.legs[index]?.name)}_第${index + 1}段`;
  }
  return `${title}.kml`;
}
