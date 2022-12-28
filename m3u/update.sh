# 更新IPTV直播源
# 从qwerttvv/Beijing-IPTV更新文件并进行替换
echo "下载 https://raw.githubusercontent.com/wuwentao/bj-unicom-iptv/master/bj-unicom-iptv.m3u"
wget https://raw.githubusercontent.com/wuwentao/bj-unicom-iptv/master/bj-unicom-iptv.m3u -O IPTV_Unicom.original.m3u
cp IPTV_Unicom.original.m3u IPTV_Unicom.m3u
echo "更新 地址"
# "rtp://"  -> "http://10.0.0.1:4022/rtp/"
sed -i '' 's#rtp://#http://10.0.0.1:4022/rtp/#g' IPTV_Unicom.m3u