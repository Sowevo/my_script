// 结束仅作用于最后一条 way，直接提交；错误交给原状态栏，恢复使用“退回一步”。
function initJourneyCut(map, options) {
  let checkRequest = null;
  async function check(point) {
    checkRequest?.abort();
    const controller = new AbortController();
    checkRequest = controller;
    try {
      const response = await fetch('/journey/cut-preview', {method:'POST',
        headers:{'Content-Type':'application/json'}, signal:controller.signal,
        body:JSON.stringify({point:[point.lat,point.lng]})});
      const result = await response.json();
      if (!response.ok) return {allowed:false, reason:result.error || '当前位置无法结束本段。'};
      if (result.revision !== options.getData()?.revision)
        return {allowed:false, reason:'行程已变化，请重新选择。'};
      return {allowed:true, reason:''};
    } catch (error) {
      return {allowed:false, reason:controller.signal.aborted ? '' : '暂时无法检查，请重新右键选择。'};
    }
  }
  async function open(point) {
    const revision = options.getData()?.revision;
    return options.runAction(async () => {
      const response = await fetch('/journey/cut', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({point:[point.lat,point.lng],revision})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '截断失败，请重试。');
      options.onChanged(result);
      options.status('已结束本段，可用“退回一步”恢复。');
    });
  }
  return {open, check, cancel() {checkRequest?.abort();}};
}
