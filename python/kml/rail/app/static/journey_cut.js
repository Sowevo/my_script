// 在当前段已选轨迹上结束，直接提交；错误交给原状态栏。
function initJourneyCut(map, options) {
  let checkRequest = null;
  async function check(point) {
    checkRequest?.abort();
    const controller = new AbortController();
    checkRequest = controller;
    try {
      const result = await options.api.cutPreview(
        {point:[point.lat,point.lng]}, {signal:controller.signal});
      if (result.revision !== options.getData()?.revision)
        return {allowed:false, reason:'行程已变化，请重新选择。'};
      return {allowed:true, reason:''};
    } catch (error) {
      return {allowed:false, reason:controller.signal.aborted ? '' : error.message || '暂时无法检查，请重新右键选择。'};
    }
  }
  async function open(point) {
    const revision = options.getData()?.revision;
    return options.runAction(async () => {
      const result = await options.api.cut({point:[point.lat,point.lng],revision});
      options.onChanged(result);
      options.status('已结束本段。');
    });
  }
  return {open, check, cancel() {checkRequest?.abort();}};
}
