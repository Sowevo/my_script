#!/bin/bash
# 需要安装 mysql-client
# mac: brew install mysql-client
# arch: yay -s mysql-clients
# fedora: sudo yum install mysql -y
backup_dir="${HOME}/backup/mysql/"

# 目标
target_db_user="root"
target_db_password="hsgz8bz"
target_db_host="192.168.21.185"
target_db_port="33066"

time="$(date +"%Y%m%d%H%M%S")"

env="dev"

# 要保留的备份天数 #
backup_day=30

Usage() {
    echo "使用帮助:"
    echo "  -e 备份环境,dev_model2,dev_model3,test_model2"
    echo "  -h 目标MYSQL主机地址,eg:192.168.1.1"
    echo "  -u 目标MYSQL账号,eg:root"
    echo "  -p 目标MYSQL密码,eg:root"
    echo "  -P 目标MYSQL端口,eg:3306"
    exit 1
}

info(){
    echo $(date +'%Y-%m-%d %T')"  从${env}环境备份数据"
    echo "地址:$source_db_host"
    echo "端口:$source_db_port"
    echo "账号:$source_db_user"
    echo "密码:$source_db_password"
    echo "======================="
    echo $(date +'%Y-%m-%d %T')"  备份到目标数据库"
    echo "地址:$target_db_host"
    echo "端口:$target_db_port"
    echo "账号:$target_db_user"
    echo "密码:$target_db_password"
    echo "======================="

}


test_mysql(){
    echo $(date +'%Y-%m-%d %T')"  测连通性"
    mysql -h${source_db_host} -P${source_db_port} -u${source_db_user} -p${source_db_password}  -e "select version();" &>/dev/null
    if [ $? -ne 0 ];then
        echo "来源数据库无法连接"
        exit 1
    fi
    mysql -h${target_db_host} -P${target_db_port} -u${target_db_user} -p${target_db_password}  -e "select version();" &>/dev/null
    if [ $? -ne 0 ];then
        echo "目标数据库无法连接"
        exit 1
    fi
}

mysql_backup()
{
    # 创建文件夹
    mkdir -p ${backup_dir}
    #进入数据库备份文件目录
    cd ${backup_dir}
    
    echo $(date +'%Y-%m-%d %T')"  备份目录${backup_dir}"
    echo $(date +'%Y-%m-%d %T')"  开始备份"

    # 要备份的数据库名
    # all_db="$(mysql -u${source_db_user} -P${source_db_port} -h${source_db_host} -p${source_db_password} -Bse 'show databases' 2>/dev/null |grep digitalthread|tr '\n' ' ')"
    # all_db="digitalthread_basicconfig digitalthread_objectbuilder digitalthread_system model_objectbuilder"
    backname=${source_db_host}.${source_db_port}.${time}
    dumpfile=${backup_dir}${backname}
    

    echo $(date +'%Y-%m-%d %T')"  开始备份:${all_db}"
    mysqldump -u${source_db_user} -P${source_db_port} -h${source_db_host} -p${source_db_password} --column-statistics=0 --add-drop-database --databases ${all_db} > ${dumpfile}.sql 2>/dev/null
    #迁移到目标库
    echo $(date +'%Y-%m-%d %T')"  开始导入"
    mysql -h${target_db_host} -P${target_db_port} -u${target_db_user} -p${target_db_password} < ${dumpfile}.sql 2>/dev/null
    #将备份数据库文件库压成ZIP文件，并删除先前的SQL文件. #
    echo $(date +'%Y-%m-%d %T')"  开始压缩${dumpfile}.sql"
    tar -czvf ${backname}.tar.gz ${backname}.sql 2>/dev/null && rm ${dumpfile}.sql 2>/dev/null
    #将压缩后的文件名存入日志。

}


delete_old_backup()
{    
    # 删除旧的备份 查找出当前目录下七天前生成的文件，并将之删除
    find ${backup_dir} -type f -mtime +${backup_day} | xargs rm -rf
}

# 切换来源的mysql
switch_env(){
    case $env in
      "221")
        # 来源
        source_db_user="agentdesigner"
        source_db_password="Agentdesigner@230424."
        source_db_host="192.168.5.248"
        source_db_port="3306"
        all_db="agentdesigner"
      ;;
      "62")
        # 来源
        source_db_user="root"
        source_db_password="nancal.123"
        source_db_host="192.168.5.62"
        source_db_port="3306"
        # 要备份的数据库名称
        all_db="agentdesigner"
      ;;
      *)
        echo "参数env错误!" Usage
        exit 1
      ;;
    esac
}

while getopts "e:h:p:u:p:" opt
do
    case $opt in
        e) env=$OPTARG;;
        h) target_db_host=$OPTARG;;
        u) target_db_user=$OPTARG;;
        p) target_db_password=$OPTARG;;
        P) target_db_port=$OPTARG;;
        ?) echo "参数错误!" Usage ;;
    esac
done

switch_env
info
test_mysql
mysql_backup
delete_old_backup
echo -e $(date +'%Y-%m-%d %T')"  备份完成...\n\n"

