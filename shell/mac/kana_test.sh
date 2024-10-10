#!/bin/bash
# 听写?



# 定义平假名和片假名数组
hiragana=("あ" "い" "う" "え" "お" "か" "き" "く" "け" "こ" "さ" "し" "す" "せ" "そ" "た" "ち" "つ" "て" "と" "な" "に" "ぬ" "ね" "の" "は" "ひ" "ふ" "へ" "ほ" "ま" "み" "む" "め" "も" "や" "ゆ" "よ" "ら" "り" "る" "れ" "ろ" "わ" "を" "ん")
katakana=("ア" "イ" "ウ" "エ" "オ" "カ" "キ" "ク" "ケ" "コ" "サ" "シ" "ス" "セ" "ソ" "タ" "チ" "ツ" "テ" "ト" "ナ" "ニ" "ヌ" "ネ" "ノ" "ハ" "ヒ" "フ" "ヘ" "ホ" "マ" "ミ" "ム" "メ" "モ" "ヤ" "ユ" "ヨ" "ラ" "リ" "ル" "レ" "ロ" "ワ" "ヲ" "ン")
romaji=("a" "i" "u" "e" "o" "ka" "ki" "ku" "ke" "ko" "sa" "shi" "su" "se" "so" "ta" "chi" "tsu" "te" "to" "na" "ni" "nu" "ne" "no" "ha" "hi" "fu" "he" "ho" "ma" "mi" "mu" "me" "mo" "ya" "yu" "yo" "ra" "ri" "ru" "re" "ro" "wa" "wo" "n")




while true; do
  # 随机选择一个假名
  random_index=$(( RANDOM % ${#hiragana[@]} ))
  selected_hiragana=${hiragana[$random_index]}
  selected_katakana=${katakana[$random_index]}
  selected_romaji=${romaji[$random_index]}

  echo "=========="
  # 输出罗马字
  echo "罗马音: $selected_romaji"
  # 朗读假名和罗马音五遍
  for i in {1..5}; do
    say -v Kyoko "$selected_hiragana"
  done

  # 提示用户按下回车进行下一个
  read -s -n 1 user_input
  # 输出平假名与片假名
  echo "平假名: $selected_hiragana"
  echo "片假名: $selected_katakana"
  if [[ $user_input != "" && $user_input != " " ]]; then
    echo "程序结束。"
    break
  fi
done
