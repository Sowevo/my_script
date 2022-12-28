#!/bin/bash
# 需要安装 mysql-client
# mac: brew install mysql-client
# arch: yay -s mysql-clients
backup_dir="${HOME}/backup/mysql/"

# 要保留的备份天数 #
backup_day=30

Usage() {
    echo "使用帮助:"
    echo "  -e 备份环境,可选dev,test,my,211"
    echo "  -o 保存文件名,非必填"
    exit 1
}

info(){
    echo $(date +'%Y-%m-%d %T')"  从${env}环境备份数据"
    echo "地址:$source_db_host"
    echo "端口:$source_db_port"
    echo "账号:$source_db_user"
    echo "密码:$source_db_password"
    echo "======================="
}


test_mysql(){
    echo $(date +'%Y-%m-%d %T')"  测连通性"
    mysql -h${source_db_host} -P${source_db_port} -u${source_db_user} -p${source_db_password}  -e "select version();" &>/dev/null
    if [ $? -ne 0 ];then
        echo "来源数据库无法连接"
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

    echo $(date +'%Y-%m-%d %T')"  开始备份:${all_db}"
    mysqldump -u${source_db_user} -P${source_db_port} -h${source_db_host} -p${source_db_password} --column-statistics=0 --add-drop-database --databases ${all_db} > ${dumpfile}.sql 2>/dev/null
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

# 处理参数
switch_param(){
    # 处理来源数据库信息
    case $env in
      "dev")
        source_db_user="digitalthread"
        source_db_password="digitalthread"
        source_db_host="192.168.5.248"
        source_db_port="3306"
      ;;
      "test")
        source_db_user="model"
        source_db_password="nancal.62ea"
        source_db_host="192.168.5.248"
        source_db_port="3307"
      ;;
      "211")
        source_db_user="nancal"
        source_db_password="nancal.123"
        source_db_host="192.168.5.211"
        source_db_port="3307"
      ;;
      "my")
        source_db_user="root"
        source_db_password="hsgz8bz"
        source_db_host="192.168.21.185"
        source_db_port="33066"
      ;;
      *)
        echo "参数env错误!"
        exit 1
      ;;
    esac

    # 处理-o参数,设置到备份路径中
    if [ ! $backname ]; then
      time="$(date +"%Y%m%d%H%M%S")"
      backname=${source_db_host}.${source_db_port}.${time}
    fi


    # 备份文件的路径(不含后缀)
    dumpfile=${backup_dir}${backname}

    # 要备份的数据库名称
    all_db="digitalthread_basicconfig digitalthread_objectbuilder digitalthread_system model_objectbuilder"
}

while getopts "e:o:" opt
do
    case $opt in
        e) env=$OPTARG;;
        o) backname=$OPTARG;;
        ?) echo "参数错误!" Usage ;;
    esac
done

switch_param
info
test_mysql
mysql_backup
delete_old_backup
echo -e $(date +'%Y-%m-%d %T')"  备份完成...\n\n"

