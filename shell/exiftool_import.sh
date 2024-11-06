#!/bin/sh
# 使用exiftool整理媒体文件


# 获取脚本所在目录
current_path="$(dirname "$(realpath "$0")")"
echo "当前路径：$current_path"

# 遍历当前目录下的所有一级目录
for dir in "$current_path"/*/ ; do
  # 去掉目录名末尾的斜杠
  dir_name="${dir%/}"

  # 获取当前目录下该一级目录的绝对路径
  source_absolute_path=$(realpath "$dir_name")

  # 根据 dir_name 的值选择目标相对路径
  case "$dir_name" in
    *"Action4" | *"Pocket3")
      relative_path="$current_path/../视频/${dir_name##*/}"
      ;;
    *)
      relative_path="$current_path/../照片/${dir_name##*/}"
      ;;
  esac

  # 判断目标相对路径目录是否存在，不存在则创建
  if [ ! -d "$relative_path" ]; then
    mkdir -p "$relative_path"
    echo "目录已创建：$relative_path"
  fi

  # 获取目标目录的绝对路径
  target_absolute_path=$(realpath "$relative_path")

  # 调用 exiftool，将 source_absolute_path 和 target_absolute_path 替换为实际路径
  exiftool -d "$target_absolute_path/%Y-%m-%d/%Y-%m-%d_%H%M%S%%-c.%%ue" "-filename<filemodifydate" "-filename<createdate" "-filename<datetimeoriginal" -r "$source_absolute_path"

  # 删除 source_absolute_path 下的所有空文件夹，但不删除 source_absolute_path 本身
  find "$source_absolute_path"/* -type d -empty -delete && echo "已删除 $source_absolute_path 下的空文件夹"

done
