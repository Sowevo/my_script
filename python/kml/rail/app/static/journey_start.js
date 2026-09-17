// 仅在用户指定起点后展示两侧候选，沿用原轨道列表。
function initJourneyStart(map, options) {
  let draft = null, base = null, marker = null, highlight = null, endpoint = null;
  const list = options.list;
  function clearHighlight() {
    if (highlight) map.removeLayer(highlight);
    if (endpoint) map.removeLayer(endpoint);
    highlight = endpoint = null;
    if (draft) options.previewArrows?.showTracks('start', draft.geometry.map(coords => ({coords,tags:draft.tags})));
  }
  function cancel() {
    const active = Boolean(draft);
    clearHighlight();
    options.previewArrows?.clear('start');
    if (base) map.removeLayer(base);
    if (marker) map.removeLayer(marker);
    base = marker = draft = null;
    if (active) options.restoreList();
  }
  function button(parent, text, action, className) {
    const control = document.createElement('button');
    control.type = 'button';
    control.className = className;
    control.textContent = text;
    control.onclick = action;
    parent.appendChild(control);
    return control;
  }
  function showHighlight(direction) {
    clearHighlight();
    highlight = L.polyline(direction.coords, {...TRACK_STYLES.highlight,interactive:false}).addTo(map);
    options.previewArrows?.showTracks('start', draft.directions.map(side => ({
      coords:side.coords, tags:draft.tags, reversed:side.span[1] < side.span[0],
      color:side.id === direction.id ? TRACK_STYLES.highlight.color : TRACK_STYLES.preview.color
    })));
    endpoint = L.circleMarker(direction.coords.at(-1), {radius:6,color:'red',interactive:false}).addTo(map);
    const label = document.createElement('span');
    label.textContent = '前进至此';
    endpoint.bindTooltip(label, {permanent:true});
  }
  async function preview(current, point) {
    const coordinates = point ? [point.lat, point.lng] : null;
    const response = await fetch('/journey/start-preview', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({way_id:current.wid,point:coordinates})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '起点预览失败');
    if (draft !== current) return;
    current.directions = data.directions;
    clearHighlight();
    if (marker) map.removeLayer(marker);
    marker = data.point ? L.circleMarker(data.point,
      {radius:7,color:'#111827',fillColor:'white',fillOpacity:1,interactive:false}).addTo(map) : null;
    list.replaceChildren();
    const title = document.createElement('b');
    title.textContent = '可选起始轨道:';
    list.appendChild(title);
    const ul = document.createElement('ul');
    ul.className = 'list-group mt-2';
    list.appendChild(ul);
    list.hidden = false;
    data.directions.forEach((direction, index) => {
      const identity = `${current.wid}-${String.fromCharCode(65 + direction.id)}`;
      const begin = () => {
        if (draft !== current || options.busy()) return;
        return options.runAction(async () => {
          const response = await fetch('/journey/start', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({way_id:current.wid,
              point:coordinates, direction:direction.id, revision:data.revision, reset:current.reset,
              replace_current:current.replaceCurrent})});
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || '开始行程失败');
          cancel();
          options.onChanged(result);
        });
      };
      const row = document.createElement('li');
      row.className = 'list-group-item';
      row.style.marginBottom = '2px';
      ul.appendChild(row);
      const choose = button(row, `${identity}（${current.name}）`, begin, 'choice-way');
      choose.onmouseenter = choose.onfocus = () => showHighlight(direction);
      choose.onmouseleave = choose.onblur = clearHighlight;
      const actions = document.createElement('span');
      actions.className = 'choice-actions';
      row.appendChild(actions);
      const advance = button(actions, '', begin, 'track-locate advance-choice');
      advance.innerHTML = '<i class="bi bi-chevron-double-right" aria-hidden="true"></i>';
      advance.title = '从此方向开始，仅加入这一条轨道';
      advance.setAttribute('aria-label', `从 ${identity} 开始`);
      const locate = button(actions, '', () => {
        showHighlight(direction);
        map.fitBounds(direction.coords, {padding:[40,40],maxZoom:18,animate:false});
      }, 'track-locate locate-choice');
      locate.innerHTML = '<i class="bi bi-crosshair" aria-hidden="true"></i>';
      locate.title = '查看这条候选轨道全貌';
      locate.setAttribute('aria-label', `查看 ${identity} 全貌`);
    });
  }
  async function select(wid, point, {replaceCurrent = false} = {}) {
    cancel();
    const response = await fetch(`/elements/way/${wid}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '轨道加载失败');
    if (!data.geometry?.length) throw new Error('这条轨道没有可用坐标。');
    options.clearReference();
    draft = {wid:Number(wid),name:data.tags?.name || '未命名',tags:data.tags || {},geometry:data.geometry,
      reset:!options.hasJourney(),replaceCurrent};
    base = L.polyline(data.geometry, TRACK_STYLES.preview).addTo(map);
    if (options.previewArrows) {
      options.previewArrows.showTracks('start', data.geometry.map(coords => ({coords, tags:draft.tags})));
    }
    await preview(draft, point);
  }
  function choosePoint(point) {
    if (!draft || options.busy()) return;
    const current = draft;
    return options.runAction(() => preview(current, point));
  }
  return {select, choosePoint, cancel, get active() {return Boolean(draft);}};
}
