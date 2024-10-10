for file in *.mp4; do
  # 集数
  episode=$(echo "$file" | grep -oP '(?<=第\s)\d+')
  # 头
  head=00:00:00
  # 尾
  tail=00:00:00

  # 删掉的开头部分
  if [[ $episode -le 44 ]]; then # 小与等于44
    head=00:02:15
  elif [[ $episode -le 46 ]]; then # 小与等于46
    head=00:02:35
  else # 大于46
    head=00:02:31
  fi

  # 删掉的结尾部分
  if [[ $episode -le 36 ]]; then # 小与等于36
    tail=00:02:15
  elif [[ $episode -le 46 ]]; then # 小与等于46
    tail=00:02:00
  else # 大于46
    tail=00:02:10
  fi

  # 总时长
  duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file")

  tail_seconds=$(echo "$tail" | awk -F: '{ print ($1 * 3600) + ($2 * 60) + $3 }')
  # 转换为整数（去掉小数部分）并减去120秒
  duration=${duration%.*}  # 去掉小数部分
  end_time=$((duration - tail_seconds))
  ffmpeg -i "$file" -ss $head -to "$end_time" -q:a 0 -map a "${file%.mp4}.mp3"
done