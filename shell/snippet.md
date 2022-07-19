## 批量操作ffmpeg
- 当前路径下的webp文件全部转换为gif
  ```shell
  for file in ./*.webp ; do ffmpeg -i $file ${file//webp/gif}; done
  ```
