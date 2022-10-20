## ffmpeg
- 当前路径下的webp文件全部转换为gif
  ```shell
  for file in ./*.webp ; do ffmpeg -i $file ${file//webp/gif}; done
  ```
## find  
- 查找某路径下名字符合某规则的文件的总大小
  ```shell
  # 在/share/CACHEDEV1_DATA/Vol1/media_volume/downloads/下查找名字包含FRDS的文件的总大小
  var1=`find /share/CACHEDEV1_DATA/Vol1/media_volume/downloads/ -iname "*FRDS*" -type f -exec du -s {} \;|awk '{print $1}'|awk '{sum1+= $1}END{print sum1}'` \
  && let "var=$var1/1024/1024" && echo $var"G"
  ```
## 其他
- 使用exiftool对照片进行整理
  ```shell
  # 使用exiftool重名文件
  # 文档 https://exiftool.org/filename.html
  # 参数 介绍
  # -ext 
  #   包含的格式
  # --ext
  #   排除的格式
  # -r
  #   递归处理文件
  # -d
  #   -d %Y-%m-%d/%Y-%m-%d_%H%M%S.%%ue
  #   指定格式化的格式
  #   %%ue 大写的文件后缀
  # "-filename<datetimeoriginal"
  #   -filename 移动文件,支持写"/"移动文件夹
  #   -directory 将文件移动到指定目录,没啥用..
  #   -testname 不移动,只打印结果
  #     后面可以跟,指定datetimeoriginal,日期从哪里获取,可选的还有 createdate,filemodifydate等
  $ exiftool -d %Y-%m-%d/%Y-%m-%d_%H%M%S.%%ue "-filename<datetimeoriginal" -r .
  
  # 在Docker中运行
  # -v /home/sowevo/图片/tmp:/work 需要将要处理的文件夹映射到/work中
  # --rm 用完就删掉这个容器
  # -e PUID=1000 -e PGID=100 指定权限
  $ docker run -v /share/CACHEDEV2_DATA/Vol2/照片/D5300:/work --rm -e PUID=1000 -e PGID=100 ltdgbchedu/exiftool \
      -d %Y-%m-%d/%Y-%m-%d_%H%M%S.%%ue  "-filename<datetimeoriginal" -r .
  ```
