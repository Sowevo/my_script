#!/usr/bin/env bash
set -ue
#CONFIGURATION
workdir="$HOME/.bg/" #Clobberful working directory
tiles=4 #Size of image: 1 2 4 8 16
#    https://himawari8.nict.go.jp/img/D531106/2d/550/2021/05/18/062000_1_0.png
url="https://himawari8.nict.go.jp/img/D531106/${tiles}d/550/"
delay=20 #Images are only available after a certain (varying) delay
outputfile="${workdir}final.png"

#DEPENDENCIES
declare -a deps=("montage" "curl" "xargs")
if [ "$(uname)" != "Darwin" ]; then
  deps+=("feh")
fi
for i in "${deps[@]}"; do
    which $i > /dev/null || (echo Please install "$i" for me to work; exit 1);
done

#SCRIPT
function cleanup {
    echo "Cleanup"
    rm -f $(for((x=0;x<$tiles;x++)); do
                for((y=0;y<$tiles;y++)); do
                    echo "$workdir${x}_${y}.png"; done; done)
}

echo Working directory: "${workdir}"

[ -d "$workdir" ] || (mkdir "$workdir" && echo "Created $workdir")

cleanup

echo "Download"
if [ "$(uname)" == "Darwin" ]; then
    time="$(date -v-${delay}M +%s)"
    url="${url}$(TZ='GMT' date -r "${time}" "+%G/%m/%d/%H")$(printf '%02d' $(echo -e a=$(TZ='GMT' date -r "${time}" '+%M') '\na-a%10' | bc))00"
else
    time="$(date +%s -d "$delay minutes ago")"
    url="${url}$(TZ='GMT' date -d "@${time}" "+%G/%m/%d/%H")$(printf '%02d' $(echo -e a=$(TZ='GMT' date -d "@${time}" '+%M') '\na-a%10' | bc))00"
fi

for((x=0;x<$tiles;x++)); do 
    for((y=0;y<$tiles;y++)); do 
        echo "${url}_${x}_${y}.png -sk -o" "$workdir${x}_${y}.png"; 
    done; 
done | xargs -P 32 -n 4 curl || (echo "Failed to download images"; exit 1)

echo "Check files"


echo "Merge"
montage -tile ${tiles} -geometry +0+0 $(
    for((y=0;y<$tiles;y++)); do
        for((x=0;x<$tiles;x++)); do
            echo "$workdir${x}_${y}.png"; done; done) "${outputfile}"

cleanup

echo "Set background"
if [ "$(uname)" == "Darwin" ]; then
    # osascript -e "tell application \"Finder\" to set desktop picture to POSIX file \"${outputfile}\""
    osascript -e "tell application \"System Events\" to tell every desktop to set picture to \"${outputfile}\""
elif [ "$DESKTOP_SESSION" == "gnome" ]; then
    echo Setting gnome background
    gsettings set org.gnome.desktop.background picture-uri "file://${outputfile}"
    gsettings set org.gnome.desktop.background picture-options 'scaled'
else
    echo Using feh
    feh --bg-max "${outputfile}"
fi
