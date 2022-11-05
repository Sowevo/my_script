# Mac初试化脚本
# 在线执行
# 解决 pt站 tracker 连不上的问题...
# This script should be run via curl:
#   zsh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/mac_init.sh)"
#   zsh -c "$(curl -fsSL https://jsd.eagleyao.com/gh/Sowevo/my_script@main/shell/mac_init.sh)"




# 0.初始化用到的变量
# 系统名称
OS="$(uname)"
# 型号
MODEL_NAME="$(system_profiler SPHardwareDataType | grep "Model Name"| cut -f 2 -d:|sed 's/[ ][ ]*//g')"
# 序列号
SERIAL_NUMBER="$(system_profiler SPHardwareDataType | grep "Serial Number"| cut -f 2 -d:|sed 's/[ ][ ]*//g')"
# 型号+序列号拼出来唯一名称
UNIQUE_NAME="${MODEL_NAME}_${SERIAL_NUMBER}"
# 自动安装brew的软件列表
RECOMMEND_APPS=(mas utools)



# 1.获取sudo权限
sudo -v -p "请输入开机密码，输入过程不显示，输入完后回车:"
# 更新sudo不过期,直到脚本完成
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# 2.判断系统版本
if [[ "$OS" != "Darwin" ]]; then
  echo "此脚本只能运行在 Mac OS"
  exit 0
fi


echo -e "开始执行\n"


# 3.判断Git是否安装,没安装的话喊他安装...
git --version > /dev/null 2>&1
if [ $? -ne 0 ];then
  sudo rm -rf "/Library/Developer/CommandLineTools/"
  echo -e "Git未安装!请安装后再运行此脚本\n在系统弹窗中点击“安装”按钮"
  echo -e "如果没有弹窗的老系统,需要自己下载安装\nhttps://sourceforge.net/projects/git-osx-installer/"
  xcode-select --install > /dev/null 2>&1
  exit 0
fi

# 4.判断brew是否安装,没安装的话喊他安装
brew --version > /dev/null 2>&1
if [ $? -ne 0 ];then
  echo -e "brew未安装!请安装后再运行此脚本"
  echo -e "1、手动安装(推荐)\n2、自动安装\n"
  echo -e "请输入序号:"
  read MY_DOWN_NUM
  case $MY_DOWN_NUM in
  2)
    echo "你选择了自动安装brew"
    zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)"
    # 需要执行 source
    # 需要处理 Warning: No remote 'origin' in /opt/homebrew/Library/Taps/homebrew/homebrew-services, skipping update!
  ;;
  *)
    echo -e "您选择了手动安装brew\n请执行以下脚本安装\n"
    echo -e "/bin/zsh -c \"\$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)\"\n"
    echo -e "本脚本将退出,安装完成再来执行!"
    exit 0
  ;;
  esac
fi
# 5.查看brew update 是否正常
echo -e "尝试执行brew update\n\n==================================="
brew update&&brew upgrade
echo -e "===================================\n\n"
echo -e "请检查brew update是否正常运行,是否有报错?"
echo -e "执行是否正常(Y/N)"
read UPDATE_SUCCESS
case $UPDATE_SUCCESS in
n|N)
  echo -e "brew update执行异常\n请修复后继续执行!"
  exit 0
;;
esac


echo -e "brew安装成功,是否安装常用软件"
echo -e "1、不安装\n2、安装推荐的软件\n3、使用brew bundle恢复软件\n"
echo -e "请输入序号:"
read BREW_INSTALL
case $BREW_INSTALL in
  2)
    echo -e "你选择了自动安装,经自动安装以下软件:\n${RECOMMEND_APPS[@]}"
    echo -e "\n\n==================================="
    brew install "${RECOMMEND_APPS[@]}"
    echo -e "===================================\n\n"
    echo -e "安装完成"
  ;;
  3)
    echo -e "你选择了brew bundle恢复"
    echo -e "请输入Brewfile的路径:"
    read BREW_FILE
    echo -e "从${BREW_FILE}恢复软件"
    echo -e "\n\n==================================="
    brew bundle --file="${BREW_FILE}"
    echo -e "===================================\n\n"
    echo -e "恢复完成"
  ;;
  esac

# TODO
# 加个自动生成brew bundle备份的脚本
# mackup的使用...
