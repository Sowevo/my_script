// 数据请求与本地操作入口。行程由页面持有，原始轨道只在此处按需加载一次。
function createJourneyApi({getData, datasetVersion, onDatasetChanged = () => {}}) {
  let version = datasetVersion, blocked = false, busy = false, generation = 0, dataGeneration = 0;
  const pageId = globalThis.crypto?.randomUUID?.() || String(Date.now()) + '-' + Math.random();
  const changedMessage = '数据源已切换，请先导出已有轨迹，再清空行程使用新数据。';
  const store = {ways:new Map(), coords:new Map(), nodeWays:new Map(), stops:new Set(), ensure};
  function mismatch(data) {
    if (data.code === 'dataset_changed' || (data.dataset_version && data.dataset_version !== version)) {
      blocked = true;
      onDatasetChanged(changedMessage);
      throw new Error(changedMessage);
    }
  }
  async function dataRequest(url, options = {}) {
    if (blocked) throw new Error(changedMessage);
    const token = dataGeneration;
    const response = await fetch(url, {...options, credentials:'omit', cache:'no-store'});
    const data = await response.json();
    if (options.signal?.aborted || token !== dataGeneration) throw new Error('行程已变化，已忽略过期结果。');
    mismatch(data);
    if (!response.ok) throw new Error(data.error || '数据读取失败。');
    return data;
  }
  function read(url, options = {}) {
    return dataRequest(url + (url.includes('?') ? '&' : '?') + 'dataset_version=' + encodeURIComponent(version),options);
  }
  function postData(url, payload, options = {}) {
    return dataRequest(url, {...options,method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...payload,dataset_version:version})});
  }
  async function ensure(ids) {
    const missing = [...new Set(ids.map(Number))].filter(id => !store.ways.has(id));
    for (let i=0;i<missing.length;i+=1000) {
      const data = await postData('/track-data',{way_ids:missing.slice(i,i+1000)});
      for (const [id,way] of Object.entries(data.ways)) store.ways.set(Number(id),way);
      for (const [id,point] of Object.entries(data.coords)) store.coords.set(Number(id),point);
      for (const [id,neighbors] of Object.entries(data.node_ways)) store.nodeWays.set(Number(id),neighbors);
      data.stops.forEach(n => store.stops.add(n));
    }
  }
  function summary(data) {
    const leg = data?.legs?.at(-1);
    return {leg_count:data?.legs?.length || 0,way_count:data?.total_path?.length || 0,
      current_way:leg?.current_way ?? null,start_way:leg?.start_way ?? null,
      active_way_count:leg?.path.length || 0,last_span:leg?.path.at(-1)?.span};
  }
  function log(operation,parameters,before,after,details,error) {
    // 日志仅传操作参数及摘要；失败不影响行程，也不传完整轨迹。
    void fetch('/diagnostics',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({page_id:pageId,operation,dataset_version:version,revision:before?.revision ?? 0,
        parameters,before:summary(before),after:summary(after),details,error,
        result:after ? {stop_reason:after.stop_reason,choices:after.choices?.slice(0,50),
          manual_confirmation_required:after.manual_confirmation_required,added_way_count:after.path?.length} : null})}).catch(() => {});
  }
  async function operate(operation,payload = {},{mutation = true,signal} = {}) {
    if (blocked) throw new Error(changedMessage);
    if (busy) throw new Error('上一项操作尚未完成，请稍后再试。');
    const snapshot = getData(), token = generation, revision = snapshot?.revision ?? 0;
    if (payload.revision !== undefined && payload.revision !== revision) throw new Error('行程已变化，请重新选择位置。');
    if (mutation) busy = true;
    const details = [], engine = new JourneyEngine(store,(event,fields) => details.push({event,...fields}));
    try {
      // 已加载轨道也检查版本，防止旧页面继续使用后端的新索引。
      await read('/dataset',{signal});
      const legs = snapshot?.legs || [];
      let result;
      switch (operation) {
        case 'advance': result = await engine.advance(legs,payload); break;
        case 'forward': {
          let wid = payload.way_id;
          if (wid === undefined) {
            const choices = (await engine.choices(legs.at(-1))).choices;
            if (choices.length !== 1) throw new Error('请选择要前进的相连轨道。');
            wid = choices[0];
          }
          result = await engine.advance(legs,{way_id:wid},true); break;
        }
        case 'undo': result = await engine.undo(legs); break;
        case 'startPreview': result = await engine.startPreview(legs,payload); break;
        case 'start': result = await engine.start(legs,payload); break;
        case 'cutPreview': result = engine.cutPreview(legs,payload); break;
        case 'cut': result = await engine.cut(legs,payload); break;
        default: throw new Error('未知行程操作。');
      }
      if (blocked) throw new Error(changedMessage);
      if (signal?.aborted || token !== generation || getData() !== snapshot)
        throw new Error('行程已变化，已忽略过期结果。');
      result.revision = revision + Number(mutation);
      result.dataset_version = version;
      if (mutation) generation++;
      log(operation,payload,snapshot,mutation ? result : snapshot,details);
      return result;
    } catch (error) {
      log(operation,payload,snapshot,snapshot,details,error.message);
      throw error;
    } finally { if (mutation) busy = false; }
  }
  async function clear() {
    if (busy) throw new Error('上一项操作尚未完成，请稍后再试。');
    busy = true;
    const before = getData();
    try {
      const response = await fetch('/dataset',{credentials:'omit',cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error('无法读取当前数据源，请稍后再试。');
      version = data.dataset_version; blocked = false; generation++; dataGeneration++;
      for (const key of ['ways','coords','nodeWays','stops']) store[key].clear();
      const result = new JourneyEngine(store).response([]);
      result.revision = (before?.revision ?? 0)+1;
      result.dataset_version = version;
      log('clear',{},before,result,[]);
      return result;
    } finally { busy = false; }
  }
  return {read,postData,clear,
    advance:payload => operate('advance',payload),
    forward:payload => operate('forward',payload),
    undo:() => operate('undo'),
    startPreview:payload => operate('startPreview',payload,{mutation:false}),
    start:payload => operate('start',payload),
    cutPreview:(payload,options = {}) => operate('cutPreview',payload,{...options,mutation:false}),
    cut:payload => operate('cut',payload),
    get blocked() {return blocked;}};
}
function startRestriction(data, selectedWay) {
  if (selectedWay !== null && selectedWay !== undefined) return '';
  return data?.legs?.at(-1)?.path.length > 1 ? '本段已加入多条轨道，只能在首条轨道阶段指定起点。' : '';
}
if (typeof module !== 'undefined') module.exports = {createJourneyApi,startRestriction};
