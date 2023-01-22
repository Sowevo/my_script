# 处理下载的评书mp3文件的tag信息

import os
import re
import eyed3
from eyed3.id3.frames import ImageFrame

# 要处理的文件目录
music_path = "/Users/sowevo/Downloads/刘兰芳 新岳飞传 全161回"

# tag中的标题,使用%03d来处理集数
title = "新岳飞传第%03d回"
# tag中的作者
artist = "刘兰芳"
# tag中的专辑名
album = "新岳飞传"
# 专辑图片路径
cover_path = "/Users/sowevo/Downloads/1395378740.jpg"

# 提取集数的正则表达式
regular = r"(\d+).mp3"

for filename in os.listdir(music_path):
    if filename.endswith(".mp3"):
        file_path = os.path.join(music_path, filename)
        audiofile = eyed3.load(file_path)
        if audiofile.tag:
            match = re.search(regular, filename)
            if match:
                episode = int(match.group(1))
                print("文件名：", filename)
                print("集数：", episode)
                print("标题:", title % episode)
                print("作者:", artist)
                print("专辑:", album)
                print("==================")

                audiofile.tag.artist = artist
                audiofile.tag.album = album
                audiofile.tag.title = title % episode
                audiofile.tag.images.set(ImageFrame.FRONT_COVER, open(cover_path, 'rb').read(), "image/jpeg")
                audiofile.tag.save(encoding='utf-8')
            else:
                raise ValueError("无法从%s中获取集数信息" % filename)