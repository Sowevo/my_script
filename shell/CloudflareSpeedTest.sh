#!/bin/sh
# 在线执行
# 解决 pt站 tracker 连不上的问题...
# This script should be run via curl:
#   sh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
#   sh -c "$(curl -fsSL https://jsd.eagleyao.com/gh/Sowevo/my_script@main/shell/CloudflareSpeedTest.sh)"
# or via wget:
#   sh -c "$(wget -qO- https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
#   sh -c "$(wget -qO- https://jsd.eagleyao.com/gh/Sowevo/my_script@main/shell/CloudflareSpeedTest.sh)"
# or via fetch:
#   sh -c "$(fetch -o - https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
#   sh -c "$(fetch -o - https://jsd.eagleyao.com/gh/Sowevo/my_script@main/shell/CloudflareSpeedTest.sh)"
work_path='/tmp'
# 创建并进入工作目录
mkdir -p ${work_path}&&cd $work_path

# 下载
wget https://download.fastgit.org/XIU2/CloudflareSpeedTest/releases/download/v2.0.3/CloudflareST_linux_amd64.tar.gz \
   -O CloudflareST_linux_amd64.tar.gz
# 解压（不需要删除旧文件，会直接覆盖，自行根据需求替换 文件名）
tar -zxf CloudflareST_linux_amd64.tar.gz
# 赋予执行权限
chmod +x CloudflareST
# 清空结果文件
rm result_hosts.txt
# 运行并经结果输出搭配result_hosts.txt文件
# -tll 平均延迟下限；只输出高于指定平均延迟的 IP，可与其他上限/下限搭配、过滤假墙 IP
./CloudflareST -tll 40 -o "result_hosts.txt"
# 如果文件未生成,退出
[[ ! -e "result_hosts.txt" ]] && echo "CloudflareST 测速失败，跳过下面步骤..." && exit 0
# 如果文件为空,退出
BESTIP=$(sed -n "2,1p" result_hosts.txt | awk -F, '{print $1}')
if [[ -z "${BESTIP}" ]]; then
    echo "CloudflareST 测速结果 IP 数量为 0，跳过下面步骤..."
    exit 0
fi

echo -e "新 IP 为 ${BESTIP}\n"
# 备份hosts
echo "开始备份 Hosts 文件（hosts_backup）..."
cp -f /etc/hosts /etc/hosts_backup
# 删除注释及注释之间的内容
echo "$(sed '/# CloudflareST_HOST_START/,/# CloudflareST_HOST_END/d' /etc/hosts)" > /etc/hosts
# 写入新的内容,注释一定要有哦
cat >> /etc/hosts << EOF
# CloudflareST_HOST_START
# 把需要加的host写到这里哦
${BESTIP}    hdarea.co
${BESTIP}    www.hdarea.co
${BESTIP}    audiences.me
${BESTIP}    t.audiences.me
${BESTIP}    www.pttime.org
${BESTIP}    tracker.m-team.cc
${BESTIP}    kp.m-team.cc
${BESTIP}    pt.btschool.club
${BESTIP}    tracker.pterclub.com
# CloudflareST_HOST_END
EOF
# 处理完成
echo "处理完成,hosts内容如下"
cat /etc/hosts
