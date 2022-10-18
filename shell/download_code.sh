#!/bin/bash


user='root'
password='hsgz8bz'
port='33066'
host='192.168.21.185'
base_path='/Users/sowevo/Downloads/'

cd $base_path

sql='SELECT download_url FROM `digitalthread_objectbuilder`.`busi_cat_node_export` WHERE generate_status = "SUCCESS" AND type = "FULL_CODE" ORDER BY update_at DESC LIMIT 1;'


export MYSQL_PWD=${password}



echo "开始获取最新代码包..."
url="$(mysql -u$user -P$port -h$host -Bse $sql)"
if [ $? -ne 0 ];then
    echo "来源数据库无法连接..."
    exit 1
fi
if [ ! -n "$url" ]; then
  echo "获取最新代码包失败..."
  exit 1
else
  echo "获取成功...链接为:"$url
fi

filename=$(basename ${url} .zip)
echo $filename

echo "开始下载..."
wget $url -q -O $base_path"code.zip"
if [ $? -ne 0 ];then
  echo "下载失败..."
  exit 1
else
  echo "下载成功..."
fi


echo "开始解压..."
unar $base_path"code.zip" -D -q -f -o $base_path$filename
if [ $? -ne 0 ];then
  echo "解压失败..."
  exit 1
else
  echo "解压成功..."
fi

# echo "修改配置..."
find $base_path$filename"/code" -name "application-dev.yml" -path "*resources*" -exec sed -i "" 's/nacos:8848/192.168.21.185:8848/g;s/password: root/password: hsgz8bz/g;s/localhost:3306/192.168.21.185:33066/g;s/host: redis/host: 192.168.21.185/g;s/password: 1@#4/password: hsgz8bz/g' {} \;

# 使用idea启动项目
echo "启动项目..."
idea $base_path$filename"/code"
