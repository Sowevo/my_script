#!/usr/bin/env bash
set -euo pipefail

# link-filtered-hardlinks
# 作用：在目标目录中为源目录里的文件创建“硬链接”，并保留目录结构。
# 默认排除：*.nef（不区分大小写）
#
# 用法：
#   link-filtered-hardlinks [--dry-run] [--exclude PATTERN ...] [--verbose] <源目录> <目标目录>
#
# 示例：
#   link-filtered-hardlinks photos photos_no_nef
#   link-filtered-hardlinks --exclude "*.cr2" photos out
#   link-filtered-hardlinks --dry-run photos out
#
# 注意：
#   硬链接要求 源目录 与 目标目录 在同一文件系统/同一分区。
#   脚本会提前检测，若跨分区会直接报错退出。
#
# 进度日志：
#   固定每处理 10 个文件输出一次进度。

print_help() {
  cat <<'EOF'
用法：
  link-filtered-hardlinks [--dry-run] [--exclude PATTERN ...] [--verbose] <源目录> <目标目录>

参数：
  <源目录>     需要扫描的原始照片目录（含子目录）
  <目标目录>   输出目录（会自动创建并保留同样的子目录结构）

选项：
  --exclude PATTERN   排除匹配 PATTERN 的文件（通配符，例如 "*.nef"），可重复多次（不区分大小写）
  --dry-run           演练模式：不实际创建目录/链接
  --verbose           打印每个文件的 ln 操作（非常刷屏，不建议大量文件时开启）
  -h, --help          显示帮助

说明：
  - 会保留源目录的子目录结构到目标目录中。
  - 默认排除：*.nef（不区分大小写）。
  - 硬链接无法跨磁盘/跨分区；若检测到跨分区会报错退出。
  - 进度日志固定每处理 10 个文件提示一次。
EOF
}

# -------------------------
# 解析命令行参数
# -------------------------
dry_run=0
verbose=0
declare -a excludes=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --verbose)
      verbose=1
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

mkdir -p "$dst"

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
# 组装 find 过滤条件
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

echo "开始处理…"
echo "  源目录：$src_abs"
echo "  目标目录：$dst_abs"
echo "  源目录文件总数：$total_files"
echo "  被排除的文件数：$excluded_files"
echo "  预计需要处理：  $included_files"
if [[ $dry_run -eq 1 ]]; then
  echo "  模式：演练（dry-run，不会实际创建目录/链接）"
else
  echo "  模式：执行（将创建硬链接）"
fi
echo "  进度日志：每处理 50 个文件提示一次"

# -------------------------
# 主流程
# -------------------------
processed=0
linked=0
skipped_exists=0
errors=0
progress_every=50

cd "$src_abs"

while IFS= read -r -d '' rel; do
  rel="${rel#./}"  # 去掉 "./"
  processed=$((processed + 1))

  target="$dst_abs/$rel"
  tdir="$(dirname "$target")"

  if [[ $dry_run -eq 0 ]]; then
    mkdir -p "$tdir"
  fi

  if [[ -e "$target" ]]; then
    skipped_exists=$((skipped_exists + 1))
  else
    if [[ $dry_run -eq 1 ]]; then
      linked=$((linked + 1))
      if [[ $verbose -eq 1 ]]; then
        echo "ln \"$src_abs/$rel\" \"$target\""
      fi
    else
      if ln "$src_abs/$rel" "$target"; then
        linked=$((linked + 1))
        if [[ $verbose -eq 1 ]]; then
          echo "ln \"$src_abs/$rel\" \"$target\""
        fi
      else
        errors=$((errors + 1))
        echo "警告：创建硬链接失败：$src_abs/$rel" >&2
      fi
    fi
  fi

  if (( processed % progress_every == 0 )); then
    echo "进度：已处理 $processed / $included_files（已链接/将链接 $linked，已存在跳过 $skipped_exists，错误 $errors）"
  fi
done < <(find "${find_expr[@]}" -print0)

# -------------------------
# 结束汇总
# -------------------------
echo "完成。"
echo "  已处理：              $processed"
echo "  已链接/将链接：       $linked"
echo "  因已存在而跳过：      $skipped_exists"
echo "  错误数：              $errors"

if [[ $dry_run -eq 1 ]]; then
  echo "提示：演练模式未做实际更改（目标目录本身可能已创建）。"
fi

exit $(( errors > 0 ? 1 : 0 ))