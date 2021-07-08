#!/bin/bash
backup_dir="/Users/sowevo/backup/mysql/"

source_db_user="digitalthread"
source_db_password="digitalthread"
source_db_host="192.168.5.248"
source_db_port="3306"


source_db_user="nancal"
source_db_password="nancal.123"
source_db_host="192.168.5.248"
source_db_port="3307"

target_db_user="root"
target_db_password="hsgz8bz"
target_db_host="192.168.21.194"
target_db_port="3306"

time="$(date +"%Y%m%d%H%M%S")"

# 要保留的备份天数 #
backup_day=10



mysql_backup()
{
    # 要备份的数据库名
    all_db="$(mysql -u${source_db_user} -P${source_db_port} -h${source_db_host} -p${source_db_password} -Bse 'show databases' 2>/dev/null |grep digitalthread|tr '\n' ' ')"
    backname=bask.${time}
    dumpfile=${backup_dir}${backname}
    

    echo $(date +'%Y-%m-%d %T')"开始备份:${all_db}"
    mysqldump -u${source_db_user} -P${source_db_port} -h${source_db_host} -p${source_db_password} --databases ${all_db} > ${dumpfile}.sql 2>/dev/null
    #迁移到目标库
    echo $(date +'%Y-%m-%d %T')"开始导入"
    mysql -h${target_db_host} -P${target_db_port} -u${target_db_user} -p${target_db_password} < ${dumpfile}.sql 2>/dev/null
    #将备份数据库文件库压成ZIP文件，并删除先前的SQL文件. #
    echo $(date +'%Y-%m-%d %T')"开始压缩${dumpfile}.sql"
    tar -czvf ${backname}.tar.gz ${backname}.sql 2>&1 && rm ${dumpfile}.sql 2>/dev/null
    #将压缩后的文件名存入日志。

}
delete_old_backup()
{    
    # 删除旧的备份 查找出当前目录下七天前生成的文件，并将之删除
    find ${backup_dir} -type f -mtime +${backup_day} | xargs rm -rf
}

# 创建文件夹
mkdir -p ${backup_dir}
#进入数据库备份文件目录
cd ${backup_dir}
mysql_backup
delete_old_backup
echo -e "备份完成...\n\n"