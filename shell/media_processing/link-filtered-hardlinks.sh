#!/usr/bin/env bash
set -euo pipefail

# link-filtered-hardlinks
# 作用：在目标目录中为源目录里的文件创建“硬链接”，并保留目录结构。
# 默认排除：*.nef（不区分大小写）
#
# 用法：
#   link-filtered-hardlinks [--dry-run] [--exclude PATTERN ...] <源目录> <目标目录>
#
# 示例：
#   link-filtered-hardlinks photos photos_no_nef
#   link-filtered-hardlinks --dry-run --exclude "*.nef" --exclude "*.cr2" photos out
#
# 注意：
#   硬链接要求 源目录 与 目标目录 在同一文件系统/同一分区。
#   脚本会提前检测，若跨分区会直接报错退出。

print_help() {
  cat <<'EOF'
用法：
  link-filtered-hardlinks [--dry-run] [--exclude PATTERN ...] <源目录> <目标目录>

参数：
  <源目录>     需要扫描的原始照片目录（含子目录）
  <目标目录>   输出目录（会自动创建并保留同样的子目录结构）

选项：
  --exclude PATTERN   排除匹配 PATTERN 的文件（通配符，例如 "*.nef"），可重复多次（不区分大小写）
  --dry-run           演练模式：只打印将执行的操作，不实际创建目录/链接
  -h, --help          显示帮助

说明：
  - 会保留源目录的子目录结构到目标目录中。
  - 默认排除：*.nef（不区分大小写）。
  - 硬链接无法跨磁盘/跨分区；若检测到跨分区会报错退出。
EOF
}

# -------------------------
# 解析命令行参数
# -------------------------
dry_run=0
declare -a excludes=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --exclude)
      [[ $# -ge 2 ]] || { echo "错误：--exclude 需要一个匹配模式（例如 \"*.nef\"）" >&2; exit 2; }
      excludes+=("$2")
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "错误：未知选项：$1" >&2
      print_help >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

[[ $# -eq 2 ]] || { print_help >&2; exit 2; }

src=$1
dst=$2

# -------------------------
# 检查源目录
# -------------------------
if [[ ! -d "$src" ]]; then
  echo "错误：源目录不存在或不是目录：$src" >&2
  exit 1
fi

# 目标目录先创建出来（如需 dry-run 完全不动文件系统，可再改）
mkdir -p "$dst"

# -------------------------
# 获取“物理路径”
# -------------------------
src_abs="$(cd "$src" && pwd -P)"
dst_abs="$(cd "$dst" && pwd -P)"

# -------------------------
# 检测是否跨分区/跨文件系统
# -------------------------
src_dev="$(df -P "$src_abs" | awk 'NR==2 {print $1}')"
dst_dev="$(df -P "$dst_abs" | awk 'NR==2 {print $1}')"

if [[ "$src_dev" != "$dst_dev" ]]; then
  echo "错误：源目录与目标目录位于不同的文件系统/分区，硬链接无法跨分区。" >&2
  echo "  源：$src_abs  （设备：$src_dev）" >&2
  echo "  目标：$dst_abs  （设备：$dst_dev）" >&2
  echo "解决办法：" >&2
  echo "  1) 把目标目录放到与源目录同一分区；或" >&2
  echo "  2) 改用软链接（ln -s）或复制（cp）。" >&2
  exit 1
fi

# -------------------------
# 组装 find 过滤条件（注意：find 这里仍然从 . 开始找）
# -------------------------
declare -a find_expr
find_expr=( . -type f )

# 默认排除 NEF（不区分大小写）
find_expr+=( ! -iname "*.nef" )

# 追加用户自定义排除（同样不区分大小写）
for pat in "${excludes[@]}"; do
  find_expr+=( ! -iname "$pat" )
done

# -------------------------
# 统计：总文件数 / 将处理文件数 / 排除数
# -------------------------
total_files=$(cd "$src_abs" && find . -type f -print | wc -l | tr -d ' ')
included_files=$(cd "$src_abs" && find "${find_expr[@]}" -print | wc -l | tr -d ' ')
excluded_files=$(( total_files - included_files ))

# -------------------------
# 主流程：遍历文件并创建硬链接（保留目录结构）
# 把 rel 前缀 "./" 去掉，避免路径里出现 /./
# -------------------------
linked=0
skipped_exists=0
errors=0

if [[ $dry_run -eq 1 ]]; then
  echo "【演练模式】不会实际创建目录/链接，只打印将执行的操作。"
  echo "源目录：$src_abs"
  echo "目标目录：$dst_abs"
fi

cd "$src_abs"

while IFS= read -r -d '' rel; do
  # rel 形如：./2017-11-11/IMG 001.jpg
  rel="${rel#./}"  # 去掉开头的 "./"

  target="$dst_abs/$rel"
  tdir="$(dirname "$target")"

  # 创建目标子目录
  if [[ $dry_run -eq 1 ]]; then
    echo "mkdir -p \"$tdir\""
  else
    mkdir -p "$tdir"
  fi

  # 如果目标已存在则跳过（避免覆盖）
  if [[ -e "$target" ]]; then
    ((skipped_exists++))
    continue
  fi

  # 创建硬链接
  if [[ $dry_run -eq 1 ]]; then
    echo "ln \"$src_abs/$rel\" \"$target\""
    ((linked++))
  else
    if ln "$src_abs/$rel" "$target"; then
      ((linked++))
    else
      ((errors++))
    fi
  fi
done < <(find "${find_expr[@]}" -print0)

# -------------------------
# 输出总结
# -------------------------
echo "完成。"
echo "  源目录：$src_abs"
echo "  目标目录：$dst_abs"
echo "  源目录文件总数：        $total_files"
echo "  被排除的文件数：        $excluded_files"
echo "  已链接/将链接的文件数： $linked"
echo "  因已存在而跳过：        $skipped_exists"
echo "  错误数：                $errors"

if [[ $dry_run -eq 1 ]]; then
  echo "提示：当前为演练模式，未对文件系统做任何实际更改（目标目录本身可能已创建）。"
fi

exit $(( errors > 0 ? 1 : 0 ))