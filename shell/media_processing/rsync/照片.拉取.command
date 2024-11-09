#!/bin/zsh

# 脚本介绍：
# 这个脚本用于将远程服务器上的照片目录同步到本地指定目录。
# 在执行同步之前，脚本会进行以下检查：
# 1. 检查当前目录下是否存在名为 `rsync.path` 的文件，作为同步的标识文件。
# 2. 检查是否安装了 `rsync` 命令，并确保其版本不低于 3.1.0。
# 如果检查通过，则使用 `rsync` 工具将远程目录同步到本地目录，并输出同步的详细信息。

# 获取脚本所在目录的绝对路径
script_directory=$(cd "$(dirname "$0")" && pwd)

# 定义远程和本地目录的路径
remote_directory="sowevo@10.0.0.3:/share/CACHEDEV2_DATA/Vol2/照片/"
local_directory="$script_directory/照片/"

# 检查是否存在 rsync.path 文件
# 如果文件不存在，提示用户创建该文件并退出脚本
if [ ! -f "$script_directory/rsync.path" ]; then
    echo "未找到 rsync.path 文件，请在同步目录中增加一个 rsync.path 文件，用来标记目标路径位置正确。"
    exit 1
fi

# 检查是否安装了 rsync 命令
# 使用 command -v 判断 rsync 是否可用，如果不可用则提示用户安装并退出脚本
if ! command -v rsync &>/dev/null; then
    echo "未检测到 rsync，请先安装 rsync。"
    exit 1
fi

# 获取 rsync 版本号
# 使用 grep 和 awk 从 rsync --version 输出中提取版本号部分
rsync_version=$(rsync --version | grep -oE "version [0-9]+\.[0-9]+\.[0-9]+" | awk '{print $2}')
# 定义最低版本要求
required_version="3.1.0"

# 检查 rsync 版本是否满足要求
# 使用 sort -V 比较 rsync_version 和 required_version，若版本低于 3.1.0 则提示用户升级
if [[ "$(echo -e "$rsync_version\n$required_version" | sort -V | head -n1)" != "$required_version" ]]; then
    echo "检测到的 rsync 版本为 $rsync_version，建议升级到 3.1.0 或更高版本。"
    exit 1
fi

# 使用 rsync 同步远程目录到本地目录
# 定义 rsync 参数 -a 表示归档模式，-v 为详细输出，-h 以人类可读的格式显示文件大小等信息，--delete 使本地与远程目录保持一致，--progress 显示进度
rsync_options="-avh --delete --progress"
# 构建 rsync 命令并输出
rsync_command="rsync $rsync_options $remote_directory $local_directory"
echo "执行 rsync 命令：$rsync_command"
# 执行 rsync 命令
eval $rsync_command
