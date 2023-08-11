#!/bin/bash
# 给字幕重命名

# 这个脚本是用来遍历指定目录下的所有文件，并按照给定的过滤条件过滤出符合条件的文件，然后将这些文件重命名为给定的新文件名格式，新文件名格式中可以包含一个数字编号，该数字编号按照文件名正序递增。
# 具体来说，这个脚本有以下功能：
# 检查用户是否输入了正确的命令行参数（目录路径，过滤规则，新文件名格式）。
# 遍历目录下的所有文件，过滤出符合过滤规则的文件。
# 将符合条件的文件按照文件名正序排序，然后依次重命名为新文件名格式中的文件名，其中新文件名格式中可以包含一个数字编号，该数字编号按照文件名正序递增。
# 在重命名文件之前，先输出原始文件名和新文件名，方便用户确认。
# 将所有文件的重命名操作结果输出到控制台。

# 判断传入参数是否为空
if [[ -z "$1" || -z "$2" || -z "$3" || ! "$3" =~ [#@] ]]; then
  echo "用法："
  echo "$0 目录路径 过滤规则 新文件名格式"
  echo ""
  echo "参数说明："
  echo "目录路径：要遍历的目录路径"
  # *.ass
  echo "过滤规则：用于过滤文件的通配符表达式"
  # 食戟之灵 - S01E# - 第@集.chi.zh-cn.ass
  echo "新文件名格式：新文件名的格式，必须包含#或@,表示要替换的数字编号,#补零2位,@不补零"
  exit 1
fi

# 获取参数
path="$1"
filter="$2"
new_filename_format="$3"

# 将 $path 转换为绝对路径
path=$(readlink -f "$path")

# 初始化计数器
counter=1

# 遍历目录下的所有文件
ls "$path" | while read file
do
  # 判断文件是否符合过滤规则
  if [[ -f "$path/$file" && "$file" == $filter ]]; then
    # 格式化计数器
    counter_formatted=$(printf "%02d" "$counter")

    # 构造新文件名
    new_filename=$(echo "$new_filename_format" | sed "s/#/$counter_formatted/" | sed "s/@/$counter/")
    new_filename=$path/$new_filename
    old_filename=$path/$file

    # 输出原始文件名和新文件名
    echo "Renaming file: $old_filename -> $new_filename"

    # 重命名文件
    mv "$old_filename" "$new_filename"

    # 更新计数器
    ((counter++))
  fi
done
