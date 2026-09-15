// 当前轨道完整保留；候选从连接点向两侧截取，不依赖节点记录方向。
function choiceViewportPoints(current, choices, budget, distance) {
  const points = [...current];
  const shared = new Set(current.map(point => JSON.stringify(point)));
  for (const choice of choices) {
    const coords = choice.coords || [];
    coords.forEach((point, index) => {
      if (!shared.has(JSON.stringify(point))) return;
      for (const direction of [-1, 1]) {
        let remaining = budget;
        for (let i = index; i + direction >= 0 && i + direction < coords.length; i += direction) {
          const a = coords[i], b = coords[i + direction];
          const length = distance(a, b);
          if (length > remaining) {
            const fraction = remaining / length;
            points.push(a.map((value, axis) => value + (b[axis] - value) * fraction));
            break;
          }
          points.push(b);
          remaining -= length;
          if (remaining <= 0) break;
        }
      }
    });
  }
  return points;
}
