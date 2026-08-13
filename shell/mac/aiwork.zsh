# 新建 AI 工作目录并启动对应 CLI（zsh 函数）
#
# 安装：写入 ~/.zshrc（只需 source 一次定义函数，不是每次调用再 source）
#   [[ -f /Users/sowevo/git/self/my_script/shell/mac/aiwork.zsh ]] \
#     && source /Users/sowevo/git/self/my_script/shell/mac/aiwork.zsh
#

aiwork() {
  local tool="${1:-}"
  if [[ -z "$tool" ]]; then
    echo "用法: aiwork <claude|codex|grok|opencode> [额外参数...]" >&2
    return 1
  fi

  case "$tool" in
    claude|codex|grok|opencode) ;;
    *)
      echo "仅支持: claude | codex | grok | opencode（收到: $tool）" >&2
      return 1
      ;;
  esac

  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "找不到命令: $tool" >&2
    return 1
  fi

  local base_dir="${HOME}/aiwork/${tool}"
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  local work_dir="${base_dir}/${stamp}"

  mkdir -p "${work_dir}" || return 1
  cd "${work_dir}" || return 1
  echo "→ 工作目录: ${work_dir}"
  command "$tool" "${@:2}"
}
