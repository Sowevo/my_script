#!/bin/bash
# 给字幕文件重命名

# 脚本功能：遍历指定目录下的所有文件，按照给定的过滤条件过滤出符合条件的文件，
# 然后将这些文件重命名为指定的新文件名格式。新文件名格式中包含一个数字编号，
# 该编号按照文件名正序递增。

# 脚本功能总结：
# 1. 检查用户输入的命令行参数（目录路径，过滤规则，新文件名格式）是否符合要求。
# 2. 遍历目录，筛选出符合过滤规则的文件。
# 3. 将文件按正序编号重命名，输出原文件名和新文件名。
# 4. 文件名格式中包含#表示编号，@表示不补零的编号。

# 用法示例：
# bash subtitle_rename.sh "/Users/xxx/path/メカクシティアクターズ" "*.ass" "目隐都市的演绎者 - S01E# - 第 @ 集.ass"

# 检查传入参数的有效性
if [[ -z "$1" || -z "$2" || -z "$3" || ! "$3" =~ [#@] ]]; then
  echo "用法："
  echo "$0 目录路径 过滤规则 新文件名格式"
  echo ""
  echo "参数说明："
  echo "  目录路径：要遍历的目录路径，例如：/a/b/c"
  echo "  过滤规则：用于过滤文件的通配符表达式，例如：*.ass"
  echo "  新文件名格式：新文件名的格式，必须包含#或@，表示要替换的数字编号"
  echo "               #补零2位，@不补零。例如：食戟之灵 - S01E# - 第@集.chi.zh-cn.ass"
  echo ""
  echo "用法示例："
  echo "  1) 将 /Users/xxx/path/目录下的所有 .ass 文件，按顺序重命名为："
  echo "     目隐都市的演绎者 - S01E# - 第@集.ass"
  echo "     命令："
  echo "         $0 \"/Users/xxx/path\" \"*.ass\" \"目隐都市的演绎者 - S01E# - 第@集.ass\""
  echo ""
  echo "  2) 将 /home/user/movies 目录下的所有 .srt 文件，按顺序重命名为："
  echo "     食戟之灵 - S01E# - 第@集.srt"
  echo "     命令："
  echo "         $0 \"/home/user/movies\" \"*.srt\" \"食戟之灵 - S01E# - 第@集.srt\""
  exit 1
fi


# 获取传入的参数
path="$1"                # 目录路径
filter="$2"              # 过滤规则（通配符）
new_filename_format="$3" # 新文件名格式

# 将目录路径转换为绝对路径
path=$(readlink -f "$path")

# 检查目录是否存在
if [[ ! -d "$path" ]]; then
  echo "错误：指定的目录路径 '$path' 不存在或无法访问。"
  exit 1
fi

# 初始化文件计数器
counter=1

# 遍历目录中的所有文件
ls "$path" | while read file
do
  # 判断文件是否符合过滤规则（例如 *.ass）
  if [[ -f "$path/$file" && "$file" == $filter ]]; then
    # 格式化计数器，补零至2位
    counter_formatted=$(printf "%02d" "$counter")

    # 构造新的文件名
    new_filename=$(echo "$new_filename_format" | sed "s/#/$counter_formatted/" | sed "s/@/$counter/")
    new_filename="$path/$new_filename"  # 新文件的绝对路径
    old_filename="$path/$file"          # 原文件的绝对路径

    # 输出原始文件名和新文件名（重命名预览）
    echo "正在重命名文件：$old_filename -> $new_filename"

    # 执行重命名操作
    mv "$old_filename" "$new_filename"

    # 更新计数器
    ((counter++))
  fi
done
