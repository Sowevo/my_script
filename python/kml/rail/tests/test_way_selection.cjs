const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const template = fs.readFileSync(__dirname+'/../app/templates/index.html','utf8');
const begin = template.indexOf('    async function selectWay(');
const end = template.indexOf('    let trackActionPending',begin);
assert.ok(begin>=0 && end>begin);

(async()=>{
  for (const [reset,options] of [[true,{}],[false,{transfer:true}],[false,{}]]) {
    const calls=[];
    const response={current_way:1,choices:[2],legs:[{path:[{way_id:1}]}]};
    let rendered=null;
    const context={fetchWays:async(...args)=>{
      calls.push(args);
      if(calls.length>1) throw new Error('页面不应自行请求第二条轨道');
      return response;
    },clearNearbyQuery(){},clearPreview(){},
    document:{getElementById:()=>({replaceChildren(){}})},
    renderWays:data=>{rendered=data;}};
    vm.createContext(context);
    vm.runInContext(template.slice(begin,end),context);
    await context.selectWay(1,reset,options);
    assert.equal(calls.length,1);
    assert.equal(calls[0][1],reset);
    assert.equal(calls[0][2],options);
    assert.equal(rendered,response);
    assert.deepEqual(rendered.choices,[2]);
  }
  console.log('首次、换乘及后续选择均单次请求，唯一候选交由本地引擎决定推进检查通过');
})().catch(error=>{console.error(error);process.exitCode=1;});
