#!/bin/bash
# 用来查找当前目录下的监控视频并使用ffmpeg将其合并
# 合并了能干嘛呀
if [[ $# -lt 1 ]] ; then
    echo "请输入查找参数 ..."
    exit 1
fi

echo "正在查找包含$1的所有文件,并将结果写入$1.txt"
find ${PWD} -path "*$1*" -iname "*.mp4" -type f -exec echo file \'file:{}\' \; |sort> $1.txt
cat $1.txt
echo "使用以下命令将视频拼接"
# 不是特别快
echo "ffmpeg -f concat -safe 0 -i ${PWD}/$1.txt -c:v copy ${HOME}/Downloads/$1.mp4"

