#!/bin/bash

# 导出
echo "开始导出..."
mysqldump -h192.168.5.248 -P3306 -udatamainline -pdatamainline --databases datamainline_basicconfig datamainline_cat datamainline_objectbuilder datamainline_system >bak.sql
# 导入
echo "开始导入..."
mysql -h192.168.21.230 -P3306 -uroot -proot < bak.sql
# 删除sql文件
echo "删除中间文件..."
rm -f bak.sql
echo "备份完成..."
