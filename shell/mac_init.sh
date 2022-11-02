# Mac初试化脚本
OS="$(uname)"


# 1.判断系统版本
if [[ "$OS" != "Darwin" ]]; then
  echo "此脚本只能运行在 Mac OS"
  exit 0
fi

# 2.获取sudo权限
sudo -v -p "请输入开机密码，输入过程不显示，输入完后回车:"
# 更新sudo不过期,直到脚本完成
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &
echo -e "开始执行\n"


# 3.判断Git是否安装,没安装的话喊他安装...
git --version > /dev/null 2>&1
# if [ $? -ne 0 ];then # TODO 条件切换回去
if [ $? -ne 0 ];then
  # sudo rm -rf "/Library/Developer/CommandLineTools/" # TODO 去掉注释
  echo -e "Git未安装!请安装后再运行此脚本\n在系统弹窗中点击“安装”按钮"
  echo -e "如果没有弹窗的老系统,需要自己下载安装\nhttps://sourceforge.net/projects/git-osx-installer/"
  xcode-select --install > /dev/null 2>&1
  exit 0
fi

# 4.判断brew是否安装,没安装的话喊他安装
brew --version > /dev/null 2>&1
# if [ $? -ne 0 ];then # TODO 条件切换回去
if [ $? -ne 1 ];then
  echo -e "Brew未安装!请安装后再运行此脚本"
  echo -e "1、手动安装(推荐)\n2、自动安装\n"
  echo -e "请输入序号:"
  read MY_DOWN_NUM
  case $MY_DOWN_NUM in
  2)
    echo "你选择了自动安装Brew"
    # zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)" # TODO 去掉注释
  ;;
  *)
    echo -e "您选择了手动安装Brew\n请执行以下脚本安装\n"
    echo -e "/bin/zsh -c \"\$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)\"\n"
    echo -e "本脚本将退出,安装完成再来执行!"
    exit 0
  ;;
  esac
fi
# 5.查看brew update 是否正常
brew update&&brew upgrade
echo -e "请检查brew update命令是否正常运行,是否有报错?"
echo -e "执行是否正常（N/Y）"
read UPDATE_SUCCESS
case $UPDATE_SUCCESS in
n|N)
  echo -e "brew update执行异常\n请修复后继续执行!"
  exit 0
;;
esac

# TODO
# brew 一些必要软件  mas...
# 引导用户输入brew bundle的备份文件路径
# 加个自动生成brew bundle备份的脚本
# mackup的使用...