# 多邻国 ADB 自动做题

ADB 读 UI 树 + 外部大模型答题（OpenAI 兼容 / DeepSeek）。

## 文件

| 文件 | 作用 |
|------|------|
| `duo_driver.py` | 读屏、点击、选课、组词/配对/小故事等驱动 |
| `duo_judge.py` | 把屏幕状态发给大模型，解析 actions |
| `duo_loop.py` | 主循环：读屏 → 判题/硬编码 → 执行 |

## 依赖

- Python 3.10+
- 本机 `adb`，手机 USB 调试已授权
- 无需第三方 pip 包（仅标准库）

## 环境变量（openai / DeepSeek）

```bash
export OPENAI_API_KEY=sk-...          # 或 DEEPSEEK_API_KEY
export OPENAI_BASE_URL=https://api.deepseek.com
export OPENAI_MODEL=deepseek-chat
```

## 用法

```bash
# 确认设备
adb devices

# 跑 1 课
python3 duo_loop.py --judge openai --lessons 1

# 多课
python3 duo_loop.py --judge openai --lessons 9 --max-steps 200

# 只读屏 / 手动驱动
python3 duo_driver.py status
python3 duo_driver.py start
```

日志默认写到当前目录下 `logs/`。

## 选课黑名单

当前章节的橙色课程优先点 `晋升传奇`。

不点：普通 `复习`、`开始收听`（用稍后选择）、跳级测试、限时星级挑战（`开玩`）。

其它「开始」类按钮默认可点（含巩固薄弱技能）。
