# !/bin/bash
# 拼阿里云盘上传的命令
# This script should be run via curl:
#   sh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/aliyunpan_upload.sh)"
#   sh -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/aliyunpan_upload.sh)"
# or via wget:
#   sh -c "$(wget -qO- https://raw.githubusercontent.com/Sowevo/my_script/main/shell/aliyunpan_upload.sh)"
#   sh -c "$(wget -qO- https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/aliyunpan_upload.sh)"
# or via fetch:
#   sh -c "$(fetch -o - https://raw.githubusercontent.com/Sowevo/my_script/main/shell/aliyunpan_upload.sh)"
#   sh -c "$(fetch -o - https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/aliyunpan_upload.sh)"

echo -e "请输入要处理的本地文件夹路径"
read -r -p "本地文件夹路径: " path
# 判断他是一个存在的文件夹
if [[ ! -d "$path" ]]; then
  echo "文件夹不存在"
  exit 1
fi
echo -e "请输入要上传的目标位置"
read -r -p "目标位置: " target

# 打印出来本地文件夹下的所有第一级文件夹
# 然后拍个序
# 然后拼接成阿里云盘上传的命令
find $path -maxdepth 1 -mindepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' file; do printf './aliyunpan upload -exn "DS_Store" -exn "\.jpg$" -exn "\.nfo$" -exn "\.png$" "%s"/ '"${target}"'  \n' "$file"; done


