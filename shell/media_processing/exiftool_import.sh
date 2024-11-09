#!/bin/sh
# 使用 exiftool 整理媒体文件

# 检查是否安装了 exiftool
if ! command -v exiftool &>/dev/null; then
    echo "未检测到 exiftool，请先安装 exiftool。"
    exit 1
fi

# 获取脚本所在目录的绝对路径
current_path="$(dirname "$(realpath "$0")")"
echo "当前路径：$current_path"

# 遍历当前目录下的所有一级目录
for dir in "$current_path"/*/ ; do
  # 去掉目录名末尾的斜杠
  dir_name="${dir%/}"

  # 获取当前一级目录的绝对路径
  source_absolute_path=$(realpath "$dir_name")

  # 根据一级目录名选择目标相对路径
  case "$dir_name" in
    *"Action4" | *"Pocket3")
      # 若目录名包含“Action4”或“Pocket3”，则归档至“视频”目录
      relative_path="$current_path/../视频/${dir_name##*/}"
      ;;
    *)
      # 其他目录归档至“照片”目录
      relative_path="$current_path/../照片/${dir_name##*/}"
      ;;
  esac

  # 检查目标目录是否存在，不存在则创建
  if [ ! -d "$relative_path" ]; then
    mkdir -p "$relative_path"
    echo "目录已创建：$relative_path"
  fi

  # 获取目标目录的绝对路径
  target_absolute_path=$(realpath "$relative_path")

  # 调用 exiftool，将文件按日期重命名并归档到目标目录
  # -d 参数指定日期格式，%Y-%m-%d 表示文件夹名为日期，文件名包含日期和时间
  # "-filename<filemodifydate" 优先使用文件修改日期重命名
  # "-filename<createdate" 其次使用文件创建日期重命名
  # "-filename<datetimeoriginal" 最后使用文件的原始拍摄日期重命名
  # -r 参数递归处理目录下所有文件
  exiftool -d "$target_absolute_path/%Y-%m-%d/%Y-%m-%d_%H%M%S%%-c.%%ue" \
           "-filename<filemodifydate" "-filename<createdate" "-filename<datetimeoriginal" -r "$source_absolute_path"

  # 删除源目录中的空文件夹，但保留源目录本身
  find "$source_absolute_path"/* -type d -empty -delete && echo "已删除 $source_absolute_path 下的空文件夹"
done
