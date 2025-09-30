#!/bin/zsh
# Mac初试化脚本

# 在线执行
# This script should be run via curl:
#   zsh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/mac/mac_init.sh)"
#   zsh -c "$(curl -fsSL https://jsd.eagleyao.com/gh/Sowevo/my_script@main/shell/mac/mac_init.sh)"


get_device_info() {
  # 获取设备名称和序列号
  device_name=$(system_profiler SPHardwareDataType | awk -F ": " '/Model Name/ {print $2}')
  serial_number=$(system_profiler SPHardwareDataType | awk '/Serial Number/ {print $4}')

  # 去除设备名称和序列号中的空格和特殊字符
  device_name_clean=$(echo "$device_name" | tr -d '[:space:]' | tr -d '[:punct:]')
  serial_number_clean=$(echo "$serial_number" | tr -d '[:space:]' | tr -d '[:punct:]')

  # 检查设备名称和序列号是否为空
  if [ -z "$device_name_clean" ] || [ -z "$serial_number_clean" ]; then
    # 返回"Unknown"表示无法获取设备信息
    echo "Unknown"
  else
    # 拼接设备名称和序列号
    result="${device_name_clean}_${serial_number_clean}"
    # 返回拼接结果
    echo "$result"
  fi
}

# 0.初始化用到的变量
# 系统名称
CURRENT_DATE=$(date +"%Y%m%d")
OS="$(uname)"
# 获取硬件信息 判断inter还是苹果M
UNAME_MACHINE="$(uname -m)"
# 类似于MacBookAir_SDKJAKJKJSA的设别名称
DEVICE_INFO=$(get_device_info)
#Mac
if [[ "$UNAME_MACHINE" == "arm64" ]]; then
  #M1
  HOMEBREW_PREFIX="/opt/homebrew"
else
  #Inter
  HOMEBREW_PREFIX="/usr/local"
fi


# 自动安装brew的软件列表
RECOMMEND_APPS=(
  git mas maven telnet unar vim wget zsh ffmpeg android-platform-tools visual-studio-code 1password
  google-chrome iina jetbrains-toolbox keka openinterminal-lite qlvideo utools
)

#判断下mac os终端是Bash还是zsh
case "$SHELL" in
  */bash*)
    if [[ -r "$HOME/.bash_profile" ]]; then
      SHELL_PROFILE="${HOME}/.bash_profile"
    else
      SHELL_PROFILE="${HOME}/.profile"
    fi
    ;;
  */zsh*)
    SHELL_PROFILE="${HOME}/.zprofile"
    ;;
  *)
    SHELL_PROFILE="${HOME}/.profile"
    ;;
esac


echo "您的设备标识是[$DEVICE_INFO]"
# 1.获取sudo权限
sudo -v -p "请输入开机密码，输入过程不显示，输入完后回车:"
# 更新sudo不过期,直到脚本完成
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# 2.判断系统版本
if [[ "$OS" != "Darwin" ]]; then
  echo "此脚本只能运行在 Mac OS"
  exit 1
fi

echo -e "开始执行\n"

# 2.1. 禁用在网络存储和U盘中.DS_Store灯文件的生成
defaults write com.apple.desktopservices DSDontWriteNetworkStores true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true
killall Finder 2>/dev/null || true

# 3.判断Git是否安装,没安装的话喊用户安装...
git --version > /dev/null 2>&1
if [ $? -ne 0 ];then
  sudo rm -rf "/Library/Developer/CommandLineTools/"
  echo -e "Git未安装!请安装后再运行此脚本\n在系统弹窗中点击“安装”按钮"
  echo -e "如果没有弹窗的老系统,需要自己下载安装\nhttps://sourceforge.net/projects/git-osx-installer/"
  xcode-select --install > /dev/null 2>&1
  exit 1
fi

# 4.判断rosetta是否安装
if [[ "$UNAME_MACHINE" == "arm64" ]]; then
  HAS_ROSETTA=$(/usr/bin/pgrep -q oahd && echo Y || echo N)
  if [[ "$HAS_ROSETTA" == "N" ]]; then
    echo -e "开始安装rosetta!"
    echo -e "\n\n==================================="
    softwareupdate --install-rosetta --agree-to-license
    echo -e "===================================\n\n"
    echo -e "rosetta安装完成"
  fi
fi

# 5.判断brew是否安装,没安装的话喊用户安装
source ${SHELL_PROFILE} 2>/dev/null # 可能刚装的,source一下试试
brew --version > /dev/null 2>&1
if [ $? -ne 0 ];then
  echo -e "brew未安装!请安装后再运行此脚本"
  echo -e "1、手动安装(推荐)\n2、自动安装\n"
  echo -e "请输入序号:"
  read MY_DOWN_NUM
  case $MY_DOWN_NUM in
  2)
    echo -e "开始安装brew!"
    echo -e "\n\n==================================="
    git config --global --add safe.directory /opt/homebrew/Library/Taps/homebrew/homebrew-core
    git config --global --add safe.directory /opt/homebrew/Library/Taps/homebrew/homebrew-cask
    git config --global --add safe.directory /opt/homebrew/Library/Taps/homebrew/homebrew-services
    
    zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)"
    
    source ${SHELL_PROFILE}
    echo -e "===================================\n\n"
    echo -e "brew安装完成"
  ;;
  *)
    echo -e "请执行以下脚本手动安装\n"
    echo -e "/bin/zsh -c \"\$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)\"\n"
    echo -e "此脚本将退出,安装完成再来执行!"
  exit 1
  ;;
  esac
fi


# 6.查看brew update 是否正常
echo -e "尝试执行brew update\n\n==================================="
brew update&&brew upgrade
echo -e "===================================\n\n"
echo -e "请检查brew update是否正常执行(Y/N)?"
read UPDATE_SUCCESS
case $UPDATE_SUCCESS in
n|N)
  echo -e "brew update执行异常\n请修复后继续执行!"
  exit 1
;;
esac

# 7.安装常用软件
echo -e "brew安装成功,是否安装常用软件"
echo -e "1、不安装\n2、安装推荐的软件\n3、使用brew bundle恢复软件\n"
echo -e "请输入序号:"
read BREW_INSTALL
case $BREW_INSTALL in
  2)
    echo -e "开始安装推荐的软件!:\n${RECOMMEND_APPS[@]}"
    echo -e "\n\n==================================="
    brew install "${RECOMMEND_APPS[@]}"
    echo -e "===================================\n\n"
    echo -e "推荐的软件安装完成!"
  ;;
  3)
    echo -e "你选择了brew bundle恢复"
    echo -e "请输入Brewfile的路径(可以直接将文件拖入终端):"
    read BREW_FILE
    echo -e "从${BREW_FILE}恢复软件"
    echo -e "\n\n==================================="
    brew bundle --file="${BREW_FILE}"
    echo -e "===================================\n\n"
    echo -e "brew bundle恢复完成!"
  ;;
  esac

# 8.安装Oh My Zsh
if [ -d "$ZSH" ]; then
  echo "恭喜！Oh My Zsh 已安装。"
else
  echo -e "是否安装 Oh My Zsh"
  echo -e "1、不安装\n2、安装\n"
  echo -e "请输入序号:"
  read OH_MY_ZSH_INSTALL
  case $OH_MY_ZSH_INSTALL in
    2)
      echo -e "开始安装 Oh My Zsh!"
      echo -e "\n\n==================================="
      export RUNZSH=no
      sh -c "$(wget -O- https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
      echo -e "===================================\n\n"
      echo -e "Oh My Zsh 安装完成!"
    ;;
    *)
      echo -e "选择不安装 Oh My Zsh。"
    ;;
  esac
fi

# 9.备份软件安装列表数据到iCloud中
echo "添加定时任务以自动备份软件列表"
echo "如果有权限弹窗,请选择允许!"
# 设置变量
LIST_DIR="${HOME}/Library/Mobile Documents/com~apple~CloudDocs/MacConfig/${DEVICE_INFO}/${CURRENT_DATE}"
BREWFILE_PATH="${LIST_DIR}/Brewfile"
APPLIST_PATH="${LIST_DIR}/AppList"

# 检查并创建目录
if [ ! -d "$LIST_DIR" ]; then
    echo "目录不存在，创建目录：${LIST_DIR}"
    mkdir -p "$LIST_DIR"
fi

# 使用定时任务
new_task1="2 * * * * ${HOMEBREW_PREFIX}/bin/brew bundle dump --describe --force --file=\"$BREWFILE_PATH\""
new_task2="3 * * * * ls -1 /Applications > \"$APPLIST_PATH\""

# 获取现有的定时任务并追加新任务
existing_tasks=$(crontab -l 2>/dev/null)  # 为了处理没有现有任务的情况，将错误输出重定向到/dev/null
# 将新的任务添加到现有任务列表中
all_tasks="${existing_tasks}"$'\n'"${new_task1}"$'\n'"${new_task2}"
# 将所有任务写回到cron表
echo "$all_tasks" | crontab -

# TODO
# mackup的使用...
