// 地图轨道样式集中定义：行程、候选、查看预览、操作高亮。
const TRACK_STYLES = {
  journey: {weight:3, opacity:1},
  candidate: {color:'#64748b', weight:4, opacity:1, dashArray:'6 5'},
  preview: {color:'#f08c00', weight:4, opacity:0.85},
  highlight: {color:'red', weight:4, opacity:1},
  arrow: {weight:3, opacity:1, interactive:false, pane:'markerPane'}
};
