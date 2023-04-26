#!/bin/sh
# 在线执行
# 解决 pt站 tracker 连不上的问题...     docker exec -it qbittorrent /bin/sh
# This script should be run via curl:
#   sh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
#   sh -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
# or via wget:
#   sh -c "$(wget -qO- https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
#   sh -c "$(wget -qO- https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
# or via fetch:
#   sh -c "$(fetch -o - https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"
#   sh -c "$(fetch -o - https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/CloudflareSpeedTest.sh)"

work_path='/tmp'

uname_os() {
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  echo "$os"
}

uname_arch() {
  arch=$(uname -m)
  case $arch in
    x86_64) arch="amd64" ;;
    x86) arch="386" ;;
    i686) arch="386" ;;
    i386) arch="386" ;;
    aarch64) arch="arm64" ;;
    armv5*) arch="armv5" ;;
    armv6*) arch="armv6" ;;
    armv7*) arch="armv7" ;;
  esac
  echo ${arch}
}

uname_os_check() {
  os=$(uname_os)
  case "$os" in
    darwin) return 0 ;;
    linux) return 0 ;;
  esac
  echo "不支持的操作系统 '$(uname -s)'."
  return 1
}

uname_arch_check() {
  arch=$(uname_arch)
  case "$arch" in
    386) return 0 ;;
    amd64) return 0 ;;
    arm64) return 0 ;;
    armv5) return 0 ;;
    armv6) return 0 ;;
    armv7) return 0 ;;
  esac
  echo "不支持的操作系统架构 '$(uname -m)'."
  return 1
}

releases_version() {
  # 获取XIU2/CloudflareSpeedTest的最新版本号
  latest_release=$(curl -s "https://api.github.com/repos/XIU2/CloudflareSpeedTest/releases/latest" | grep -o '"tag_name":.*' | sed 's/"tag_name": "//;s/",//')
  # 如果获取最新版本号的过程中出错，设置默认值为 "v2.2.2"
  if [ -z "$latest_release" ]; then
    latest_release="v2.2.2"
  fi
}

download() {
  # 创建并进入工作目录
  mkdir -p ${work_path}&&cd $work_path
  echo "开始下载:https://ghproxy.com/https://github.com/XIU2/CloudflareSpeedTest/releases/download/${latest_release}/CloudflareST_${os}_${arch}.tar.gz"
  # 下载
  wget https://ghproxy.com/https://github.com/XIU2/CloudflareSpeedTest/releases/download/${latest_release}/CloudflareST_linux_amd64.tar.gz \
     -O CloudflareST_linux_amd64.tar.gz
  # 解压（不需要删除旧文件，会直接覆盖，自行根据需求替换 文件名）
  tar -zxf CloudflareST_linux_amd64.tar.gz
  # 赋予执行权限
  chmod +x CloudflareST
  # 清空结果文件
  rm -f result_hosts.txt
}

run() {
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
}


uname_os_check
uname_arch_check
releases_version
download
run
