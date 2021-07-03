#!/bin/bash

# 导出
echo "开始导出..."
mysqldump -h192.168.5.248 -P3306 -udigitalthread -pdigitalthread --databases digitalthread_objectbuilder digitalthread_basicconfig digitalthread_cat digitalthread_microservice digitalthread_system >bak.sql
# 导入
echo "开始导入..."
mysql -hdev.nancal.co -P3306 -uroot -phsgz8bz < bak.sql
# 删除sql文件
echo "删除中间文件..."
rm -f bak.sql
echo "备份完成..."
