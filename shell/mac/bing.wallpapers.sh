#!/bin/bash
# 下载bing的每日壁纸

# 指定一个工作路径
BASEDIR="/Users/sowevo/Pictures/bing"
cd "$BASEDIR"

bing="https://www.bing.com"

# 参数确定从哪一天开始。0是今天
xmlURL="https://www.bing.com/HPImageArchive.aspx?format=xml&idx=0&n=1&mkt=zh-CN"

# 清晰度可选项 "_1024x768" "_1280x720" "_1366x768" "_1920x1200" "_1920x1080" "_UHD"
picRes="_UHD"


# 扩展名
picExt=".jpg"

# XML 内容
data=$(curl -s $xmlURL)

if [ -n "$data" ]
then
picURL=$(cut -d '>' -f13 <<< "$data")
picURL=$(cut -d '<' -f 1 <<< "$picURL")
picURL=$bing$picURL$picRes$picExt

date=$(cut -d '>' -f5 <<< "$data")
date=$(cut -d '<' -f1 <<< "$date")

name=$(cut -d '>' -f15 <<< "$data")
name=$(cut -d '<' -f 1 <<< "$name")
name=$(cut -d '(' -f 1 <<< "$name")

len=${#name}

file="$date - ${name:0:len-1}$picExt"
fullpath="$BASEDIR/$file"
if [ -f "$file" ]
then
    filesize=$(wc -c < "$file")
    filesize=$(($filesize)) # parseInt
    actualsize="$(curl -s -L -I $picURL | awk 'tolower ($1) ~ /^content-length/ { print $2 }')"
    actualsize=$(echo $actualsize | sed "s/$(printf '\r')\$//") # remove carriage return on macOS

    if [ "$filesize" -eq "$actualsize" ]
    then
        echo "$(date) - '$file' already downloaded"
    else
        curl -s "$picURL" > "$file"
        echo "$(date) - image saved as $file"
    fi
else
    curl -s "$picURL" > "$file"
    echo "$(date) - image saved as $file"
    
fi
osascript -e "tell application \"System Events\" to tell every desktop to set picture to \"$fullpath\""
# osascript -e "tell application \"System Events\" to tell desktop 1 to set picture to \"$fullpath\""
else
echo "$(date) - connection failed"
fi 
