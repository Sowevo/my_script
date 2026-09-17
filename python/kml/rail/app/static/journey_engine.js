// 行程算法只在浏览器执行。store 是页面已加载的原始轨道，不保存行程副本。
class JourneyEngine {
  constructor(store, diagnostic = () => {}) { this.store = store; this.diagnostic = diagnostic; }
  nodes(id) { return this.store.ways.get(Number(id))?.nodes || []; }
  meta(id) { return this.store.ways.get(Number(id))?.meta || {}; }
  raw(item) {
    const points = this.nodes(item.way_id).map(n => this.store.coords.get(n));
    if (points.length < 2 || points.some(p => !p)) throw new Error('这条轨道缺少完整坐标，无法计算行程。');
    return points;
  }
  static distance(a, b) {
    const r = Math.PI / 180, dlat = (b[0] - a[0]) * r, dlon = (b[1] - a[1]) * r;
    return 6371000 * 2 * Math.asin(Math.min(1, Math.sqrt(Math.sin(dlat / 2) ** 2 +
      Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dlon / 2) ** 2)));
  }
  static interpolate(points, position) {
    const i = Math.min(Math.floor(position), points.length - 2), t = position - i;
    return points[i].map((v, axis) => v + t * (points[i + 1][axis] - v));
  }
  static slice(points, start, end) {
    if (Math.abs(start - end) < 1e-9) return [];
    const low = Math.min(start, end), high = Math.max(start, end);
    const line = [this.interpolate(points, low)];
    for (let i = Math.floor(low) + 1; i < Math.ceil(high); i++) line.push(points[i]);
    line.push(this.interpolate(points, high));
    return start < end ? line : line.reverse();
  }
  coords(item) { const p = this.raw(item); return item.span ? JourneyEngine.slice(p, ...item.span) : p; }
  keptNodes(item) {
    const nodes = this.nodes(item.way_id), span = item.span || [0, nodes.length - 1];
    return nodes.slice(Math.ceil(Math.min(...span)), Math.floor(Math.max(...span)) + 1);
  }
  directions(path, index) {
    const item = path[index];
    if (item.span) return [item.span];
    const nodes = this.nodes(item.way_id), end = nodes.length - 1;
    if (nodes[0] !== nodes[end]) {
      if (index) {
        const previous = path[index - 1];
        const shared = [nodes[0], nodes[end]].filter(n => previous.span ?
          JourneyEngine.distance(this.store.coords.get(n), this.coords(previous).at(-1)) < .1 :
          this.keptNodes(previous).includes(n));
        if (shared.length === 1) return shared[0] === nodes[0] ? [[0, end]] : [[end, 0]];
      }
      if (index + 1 < path.length) {
        const shared = [nodes[0], nodes[end]].filter(n => this.keptNodes(path[index + 1]).includes(n));
        if (shared.length === 1) return shared[0] === nodes[0] ? [[end, 0]] : [[0, end]];
      }
    }
    return [[0, end], [end, 0]];
  }
  loopClosed(leg) {
    const path = leg.path, item = path.at(-1), nodes = this.nodes(item.way_id);
    const directions = this.directions(path, path.length - 1);
    if (!item.span && nodes[0] === nodes.at(-1)) return true;
    if (directions.length !== 1) {
      // 两端都接回前一条时，闭环已完成。
      return path.length > 1 && [nodes[0], nodes.at(-1)].every(n => this.keptNodes(path.at(-2)).includes(n));
    }
    const [start, end] = directions[0];
    if (!Number.isInteger(end)) return false;
    const exit = nodes[end];
    if (path.slice(0, -1).some(old => this.keptNodes(old).includes(exit))) return true;
    for (let i = Math.ceil(Math.min(start, end)); i <= Math.floor(Math.max(start, end)); i++)
      if (i !== end && nodes[i] === exit) return true;
    return false;
  }
  async choices(leg) {
    if (!leg) return {choices:[], stop_reason:''};
    if (this.loopClosed(leg)) return {choices:[], stop_reason:'前进端已接回本段走过的轨迹，本段结束。'};
    const item = leg.path.at(-1), nodes = this.nodes(item.way_id);
    if (item.span) {
      const [start, end] = item.span, terminal = end > start ? nodes.length - 1 : 0;
      if (Math.abs(end - terminal) > 1e-9)
        return {choices:[item.way_id], stop_reason:'可继续当前轨道剩余部分，或开始下一段。'};
    }
    const visited = new Set(leg.path.map(i => i.way_id));
    const neighbors = [...new Set(this.keptNodes(item).flatMap(n => this.store.nodeWays.get(n) || []))]
      .filter(id => !visited.has(id)).sort((a,b) => a-b);
    await this.store.ensure(neighbors);
    return {choices:neighbors, stop_reason:neighbors.length ? '' : '本段没有更多相连轨道，可搜索轨道开始下一段。'};
  }
  canAuto(leg, candidate) {
    const path = leg.path, item = path.at(-1), nodes = this.nodes(item.way_id);
    const spans = this.directions(path, path.length - 1);
    if (spans.length !== 1) return false;
    const [start, end] = spans[0];
    if (candidate === item.way_id) return Boolean(item.span) && end !== (end > start ? nodes.length - 1 : 0);
    if (!Number.isInteger(end) || ![0, nodes.length - 1].includes(end)) return false;
    const following = this.nodes(candidate), shared = [...new Set(nodes.filter(n => following.includes(n)))];
    return shared.length === 1 && shared[0] === nodes[end] && [following[0], following.at(-1)].includes(nodes[end]);
  }
  async advance(legs, payload, one = false) {
    let wid = Number(payload.way_id);
    if (!Number.isSafeInteger(wid)) throw new Error('请选择有效的轨道 ID。');
    await this.store.ensure([wid]);
    this.raw({way_id:wid});
    const updated = structuredClone(payload.reset ? [] : legs);
    if (payload.reset && payload.transfer) throw new Error('不能同时重新开始和添加换乘。');
    if (payload.transfer && !updated.length) throw new Error('请先开始第一段行程，再添加换乘。');
    const newLeg = payload.transfer || !updated.length;
    let leg = updated.at(-1);
    if (newLeg) {
      leg = {name:this.meta(wid).tags?.name || '未命名轨道', start_way:wid, current_way:wid, path:[], transfer_label:''};
      updated.push(leg);
    } else if (!(await this.choices(leg)).choices.includes(wid))
      throw new Error('请选择当前可选轨道；不相连的轨道请通过添加换乘进入。');
    const travelled = [];
    let result;
    while (true) {
      this.raw({way_id:wid});
      const last = leg.path.at(-1), item = {way_id:wid, type:travelled.length ? 'auto' : 'manual'};
      if (last?.way_id === wid && last.span) {
        const [start, end] = last.span;
        item.span = [end, end > start ? this.nodes(wid).length - 1 : 0];
      } else if (last?.span) {
        // 只有确实接在已知前进端时才继承方向；折返仍允许手动确认。
        const end = last.span[1], node = Number.isInteger(end) ? this.nodes(last.way_id)[end] : null;
        const nodes = this.nodes(wid);
        if (node !== null && [nodes[0], nodes.at(-1)].includes(node))
          item.span = nodes[0] === node ? [0, nodes.length - 1] : [nodes.length - 1, 0];
      }
      leg.path.push(item);
      leg.current_way = wid;
      travelled.push(wid);
      result = await this.choices(leg);
      if (newLeg || one || result.choices.length !== 1) break;
      if (!this.canAuto(leg, result.choices[0])) {
        result.stop_reason = '下一条可能需要折返或连接方向不明确，请手动确认。';
        result.manual_confirmation_required = true;
        break;
      }
      wid = result.choices[0];
      if (travelled.length % 30 === 0) await new Promise(resolve => setTimeout(resolve, 0));
    }
    return this.response(updated, {...result, path:travelled});
  }
  async undo(legs) {
    const updated = structuredClone(legs);
    if (updated.length) {
      updated.at(-1).path.pop();
      if (!updated.at(-1).path.length) updated.pop();
      if (updated.length) updated.at(-1).current_way = updated.at(-1).path.at(-1).way_id;
    }
    return this.response(updated, await this.choices(updated.at(-1)));
  }
  project(points, point, low = 0, high = points.length - 1) {
    const cosine = Math.cos(point[0] * Math.PI / 180);
    let best = null;
    for (let i = Math.floor(low); i < Math.min(Math.ceil(high), points.length - 1); i++) {
      const a = points[i], b = points[i + 1];
      const dx = (b[1] - a[1]) * cosine, dy = b[0] - a[0], length = dx * dx + dy * dy;
      if (!length) continue;
      const t = ((point[1] - a[1]) * cosine * dx + (point[0] - a[0]) * dy) / length;
      const position = Math.max(low, Math.min(high, i + Math.max(0, Math.min(1, t))));
      const distance = JourneyEngine.distance(point, JourneyEngine.interpolate(points, position));
      if (!best || distance < best.distance) best = {position, distance};
    }
    return best;
  }
  snap(wid, position, low, high) {
    const points = this.raw({way_id:wid}), point = JourneyEngine.interpolate(points, position);
    const stops = this.nodes(wid).flatMap((n,i) => this.store.stops.has(n) && low <= i && i <= high ?
      [{position:i, distance:JourneyEngine.distance(point, points[i])}] : []).sort((a,b) => a.distance-b.distance);
    return stops.length && stops[0].distance <= 25 ? {position:stops[0].position, snapped:true} : {position, snapped:false};
  }
  validatePoint(point) {
    if (!Array.isArray(point) || point.length !== 2 || !point.every(Number.isFinite) ||
        Math.abs(point[0]) > 90 || Math.abs(point[1]) > 180) throw new Error('请选择有效的地图位置。');
  }
  restrictStart(legs, payload) {
    if (payload.replace_current && (!legs.length || legs.at(-1).path.length !== 1 ||
        legs.at(-1).path[0].way_id !== Number(payload.way_id)))
      throw new Error('本段已加入多条轨道，只能在首条轨道阶段指定起点。');
  }
  async startPreview(legs, payload) {
    this.restrictStart(legs, payload);
    const wid = Number(payload.way_id);
    await this.store.ensure([wid]);
    const points = this.raw({way_id:wid}), end = points.length - 1;
    if (!payload.point) return {point:null,snapped:false,directions:[
      {id:0,span:[end,0],coords:[...points].reverse()}, {id:1,span:[0,end],coords:points}]};
    this.validatePoint(payload.point);
    const projection = this.project(points, payload.point);
    this.diagnostic('start_projection', {way_id:wid, click:payload.point, distance_m:projection?.distance, max_distance_m:150});
    if (!projection || projection.distance > 150) throw new Error('请在已选轨道上点击起点（距离不超过 150 米）。');
    const {position,snapped} = this.snap(wid, projection.position, 0, end);
    this.diagnostic('start_result', {way_id:wid,position,snapped,point:JourneyEngine.interpolate(points,position)});
    return {point:JourneyEngine.interpolate(points,position),snapped,directions:[0,end].flatMap((terminal,id) =>
      Math.abs(position-terminal) < 1e-9 ? [] : [{id,span:[position,terminal],coords:JourneyEngine.slice(points,position,terminal)}])};
  }
  async start(legs, payload) {
    const preview = await this.startPreview(legs, payload);
    const direction = preview.directions.find(d => d.id === payload.direction);
    if (!direction) throw new Error('请点击想走的一侧。');
    const updated = structuredClone(payload.reset ? [] : legs), wid = Number(payload.way_id);
    const leg = {name:this.meta(wid).tags?.name || '未命名轨道', start_way:wid,current_way:wid,
      transfer_label:'',path:[{way_id:wid,type:'manual',span:direction.span}]};
    if (payload.replace_current) updated[updated.length-1] = leg;
    else updated.push(leg);
    return this.response(updated, {...await this.choices(leg),path:[wid]});
  }
  cutPreview(legs, payload) {
    if (!legs.length) throw new Error('请先选择轨道。');
    const point = payload.point;
    this.validatePoint(point);
    const path = legs.at(-1).path;
    let nearest = null;
    path.forEach((item,index) => {
      const spans = this.directions(path,index), points = this.raw(item);
      const projection = this.project(points, point, Math.min(...spans[0]), Math.max(...spans[0]));
      if (projection && (!nearest || projection.distance < nearest.distance - 1e-7))
        nearest = {...projection,index,spans,points};
    });
    this.diagnostic('end_projection', {click:point,distance_m:nearest?.distance,path_index:nearest?.index,
      way_id:nearest ? path[nearest.index].way_id : null,max_distance_m:150});
    if (!nearest || nearest.distance > 150) throw new Error('点击位置距本段已选轨道超过 150 米，请靠近本段轨迹选择终点。');
    if (nearest.spans.length !== 1) throw new Error('尚未确定行进方向，请先用“从此开始本段”选择起点和方向。');
    let {index,points} = nearest, [start,end] = nearest.spans[0];
    const snapped = this.snap(path[index].way_id,nearest.position,Math.min(start,end),Math.max(start,end));
    let position = snapped.position;
    if (Math.abs(position-start) < 1e-9 && index) {
      const previous = this.raw(path[index-1]), spans = this.directions(path,index-1);
      if (spans.length === 1 && JourneyEngine.distance(JourneyEngine.interpolate(previous,spans[0][1]),
          JourneyEngine.interpolate(points,position)) < .1) {
        index--; points = previous; [start,end] = spans[0]; position = end;
      }
    }
    if (Math.abs(position-start) < 1e-9) throw new Error('终点落在本段起点，请用“退回一条轨道”缩短行程。');
    if (Math.abs(position-end) < 1e-9 && index === path.length-1) throw new Error('此处已经是本段终点。');
    const candidate = {id:0,path_index:index,way_id:path[index].way_id,side:'end',span:[start,position],
      point:JourneyEngine.interpolate(points,position),snapped:snapped.snapped,distance:nearest.distance,
      removed:[JourneyEngine.slice(points,position,end),...path.slice(index+1).map(i => this.coords(i))].filter(p => p.length >= 2)};
    this.diagnostic('end_result', {way_id:candidate.way_id,path_index:index,span:candidate.span,point:candidate.point,snapped:candidate.snapped,
      removed_way_count:path.length-index-1});
    return {candidates:[candidate]};
  }
  async cut(legs, payload) {
    const candidate = this.cutPreview(legs,payload).candidates[0], updated = structuredClone(legs), leg = updated.at(-1);
    leg.path = leg.path.slice(0,candidate.path_index+1);
    leg.path.at(-1).span = candidate.span;
    leg.current_way = leg.path.at(-1).way_id;
    return this.response(updated,await this.choices(leg));
  }
  outward(nodes,index,step) {
    const origin = this.store.coords.get(nodes[index]);
    if (!origin) return null;
    const scale = 111195, longitude = scale * Math.cos(origin[0]*Math.PI/180);
    let previous = origin, remaining = 30, vector = null;
    for (let i=index+step; i>=0 && i<nodes.length; i+=step) {
      const point = this.store.coords.get(nodes[i]);
      if (!point) break;
      const length = Math.hypot((point[1]-previous[1])*longitude,(point[0]-previous[0])*scale);
      const fraction = length ? Math.min(1,remaining/length) : 1;
      const end = previous.map((v,axis) => v+(point[axis]-v)*fraction);
      vector = [(end[1]-origin[1])*longitude,(end[0]-origin[0])*scale];
      remaining -= length;
      if (remaining <= 0) break;
      previous = point;
    }
    return vector && Math.hypot(...vector) > 0 ? vector : null;
  }
  recommend(path,choices) {
    if (!path.length) return null;
    const item = path.at(-1), spans = this.directions(path,path.length-1);
    if (spans.length !== 1) return null;
    const [entry,exit] = spans[0], direction = Math.sign(exit-entry), nodes = this.nodes(item.way_id);
    const tags = this.meta(item.way_id).tags || {}, service = new Set(['yard','siding','spur','crossover']);
    const compare = (a,b) => { for (let i=0;i<a.length;i++) if (a[i]!==b[i]) return a[i]-b[i]; return 0; };
    const ranked = [];
    for (const wid of choices) {
      const candidate = this.nodes(wid), other = this.meta(wid).tags || {};
      if (new Set(nodes.filter(n => candidate.includes(n))).size !== 1) continue;
      const scores = [];
      nodes.forEach((node,i) => {
        if ((i-entry)*direction <= 0 || i < Math.min(entry,exit) || i > Math.max(entry,exit)) return;
        const backward = this.outward(nodes,i,-direction);
        if (!backward) return;
        candidate.forEach((n,j) => {
          if (n!==node) return;
          for (const step of [-1,1]) {
            const out = this.outward(candidate,j,step);
            if (!out) continue;
            const cosine = -(backward[0]*out[0]+backward[1]*out[1])/(Math.hypot(...backward)*Math.hypot(...out));
            if (cosine<=0) continue;
            scores.push([Number(i!==exit),Number(!service.has(tags.service)&&service.has(other.service)),
              Number(!(tags.name && tags.name===other.name)),Math.acos(Math.max(-1,Math.min(1,cosine)))]);
          }
        });
      });
      if (scores.length) ranked.push({wid,score:scores.sort(compare)[0]});
    }
    ranked.sort((a,b) => compare(a.score,b.score));
    if (!ranked.length) return null;
    if (ranked.length>1 && ranked[0].score.slice(0,3).every((n,i) => n===ranked[1].score[i]) &&
        Math.abs(ranked[0].score[3]-ranked[1].score[3])<1e-6) return null;
    return ranked[0].wid;
  }
  response(legs, result = {}) {
    const choices = result.choices || [], path = result.path || [], active = legs.at(-1)?.path || [];
    const recommended = this.recommend(active,choices);
    const track = id => ({id,coords:this.raw({way_id:id}),meta:this.meta(id)});
    const choiceCoords = choices.map(track);
    const last = active.at(-1);
    for (const choice of choiceCoords) {
      if (choice.id === recommended) choice.recommend = true;
      if (choice.id === last?.way_id && last.span) {
        const [start,end] = last.span, terminal = end>start ? this.nodes(last.way_id).length-1 : 0;
        choice.coords = JourneyEngine.slice(this.raw(last),end,terminal); choice.reversed = end>terminal;
      }
    }
    return {...result, legs:legs.map(leg => ({...leg,colour_candidates:[this.meta(leg.start_way).tags?.colour]})),
      total_path:legs.flatMap(leg => leg.path),active_path:active,current_way:legs.at(-1)?.current_way ?? null,
      choices,path,visited_path:path,stop_reason:result.stop_reason || '',choice_coords:choiceCoords,path_coords:path.map(track),
      undo:{kind:'way',coords:last ? [this.coords(last)] : []},
      total_path_coords:legs.flatMap((leg,index) => leg.path.map(item => ({id:item.way_id,coords:this.coords(item),
        reversed:Boolean(item.span && item.span[1]<item.span[0]),meta:this.meta(item.way_id),type:item.type,leg:index})))};
  }
}
if (typeof module !== 'undefined') module.exports = {JourneyEngine};
