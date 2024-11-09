#!/bin/bash
# 下载 Bing 每日壁纸并设置为桌面背景

# 指定图片保存的目录路径
BASEDIR="/Users/sowevo/Pictures/bing"
mkdir -p "$BASEDIR"  # 如果目录不存在则创建
cd "$BASEDIR"

# Bing 基础 URL
bing="https://www.bing.com"

# Bing 壁纸信息的 XML URL，指定从今天（idx=0）获取最新壁纸
xmlURL="https://www.bing.com/HPImageArchive.aspx?format=xml&idx=0&n=1&mkt=zh-CN"

# 壁纸清晰度选项："_1024x768" "_1280x720" "_1366x768" "_1920x1200" "_1920x1080" "_UHD"
picRes="_UHD"

# 壁纸扩展名
picExt=".jpg"

# 获取 XML 数据
data=$(curl -s "$xmlURL")

# 检查是否成功获取数据
if [ -n "$data" ]; then
    # 提取图片的 URL 路径、日期、名称
    picURL=$(echo "$data" | sed -n 's/.*<url>\(.*\)<\/url>.*/\1/p')
    picURL="$bing$picURL$picRes$picExt"

    date=$(echo "$data" | sed -n 's/.*<startdate>\(.*\)<\/startdate>.*/\1/p')

    # 提取名称并去除特殊字符
    name=$(echo "$data" | sed -n 's/.*<copyright>\(.*\)<\/copyright>.*/\1/p')
    name=$(echo "$name" | cut -d '(' -f 1)  # 去掉名称中的括号部分

    # 格式化保存文件的名称
    file="$date - ${name%?}$picExt"
    fullpath="$BASEDIR/$file"

    # 检查图片文件是否已存在
    if [ -f "$file" ]; then
        # 获取现有文件的大小，若为空则赋值为0
        filesize=$(wc -c < "$file" | tr -d ' ')
        filesize=${filesize:-0}

        # 获取目标文件的实际大小，若为空则赋值为0
        actualsize=$(curl -s -L -I "$picURL" | awk '/^Content-Length/ {print $2}' | tr -d '\r')
        actualsize=${actualsize:-0}

        # 比较文件大小，若匹配则不重复下载
        if [ "$filesize" -eq "$actualsize" ]; then
            echo "$(date) - 壁纸 '$file' 已下载"
        else
            curl -s "$picURL" > "$file"
            echo "$(date) - 壁纸保存为 $file"
        fi
    else
        # 下载并保存图片
        curl -s "$picURL" > "$file"
        echo "$(date) - 壁纸保存为 $file"
    fi

    # 设置图片为桌面背景
    osascript -e "tell application \"System Events\" to tell every desktop to set picture to \"$fullpath\""
else
    echo "$(date) - 无法连接 Bing 服务器"
fi
