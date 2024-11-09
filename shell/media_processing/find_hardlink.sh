#!/bin/bash
# 脚本名称：find_hardlink.sh
# 功能：查找指定文件或目录的所有硬链接
# 使用方法：find_hardlink.sh <fileOrDirToFindFor> [additionalFilesOrDirs...]
# 说明：
#    - 该脚本接收一个或多个文件或目录路径作为参数，逐个查找硬链接。
#    - 对于每个输入路径，脚本会：
#         1. 检查路径是否可访问；
#         2. 获取文件的 inode 号和挂载点；
#         3. 查找与该 inode 号匹配的所有硬链接文件；
#         4. 输出所有硬链接文件的路径。
# 示例：./find_hardlink.sh /path/to/file /another/path/to/file

# 检查是否提供了至少一个参数
if [[ $# -lt 1 ]] ; then
    echo "用法：find_hardlink.sh <fileOrDirToFindFor> [additionalFilesOrDirs...]"
    echo "说明："
    echo "    该脚本用于查找指定文件或目录的硬链接。"
    echo "    请至少提供一个文件或目录路径作为参数。"
    echo "示例："
    echo "    ./find_hardlink.sh /path/to/file /another/path/to/file"
    exit 1
fi

# 逐个处理传入的文件或目录路径
while [[ $# -ge 1 ]] ; do
    echo "正在处理：'$1'"

    # 检查文件或目录是否可访问
    if [[ ! -r "$1" ]] ; then
        echo "   无法访问：'$1'"
    else
        # 获取文件的硬链接数量、inode号和挂载点
        numlinks=$(ls -ld "$1" | awk '{print $2}')
        inode=$(ls -id "$1" | awk '{print $1}' | head -1)
        device=$(df "$1" | tail -1 | awk '{print $5}')
        echo "   '$1' 的 inode 号为 ${inode}，位于挂载点 '${device}'"

        # 查找该 inode 的所有硬链接，并输出路径
        find ${device} -inum ${inode} 2>/dev/null | sed 's/^/        /'
    fi
    shift
done
