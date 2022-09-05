## 批量操作ffmpeg
- 当前路径下的webp文件全部转换为gif
  ```shell
  for file in ./*.webp ; do ffmpeg -i $file ${file//webp/gif}; done
  ```
- 查找某路径下名字符合某规则的文件的总大小
  ```shell
  # 在/share/CACHEDEV1_DATA/Vol1/media_volume/downloads/下查找名字包含FRDS的文件的总大小
  var1=`find /share/CACHEDEV1_DATA/Vol1/media_volume/downloads/ -iname "*FRDS*" -type f -exec du -s {} \;|awk '{print $1}'|awk '{sum1+= $1}END{print sum1}'` \
  && let "var=$var1/1024/1024" && echo $var"G"
  ```
