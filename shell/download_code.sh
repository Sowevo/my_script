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



echo "开始下载..."
wget $url -q -O $base_path"code.zip"
if [ $? -ne 0 ];then
  echo "下载失败..."
  exit 1
else
  echo "下载成功..."
fi


echo "开始解压..."
rm -rf $base_path"code"
unzip -q $base_path"code.zip" -d $base_path"code"
if [ $? -ne 0 ];then
  echo "解压失败..."
  exit 1
else
  echo "解压成功..."
  exit 0
fi