# !/bin/bash

# 一键生成TLS和CA证书
# This script should be run via curl:
#   sh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/auto-generate-docker-tls-ca.sh)"
#   sh -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/auto-generate-docker-tls-ca.sh)"
# or via wget:
#   sh -c "$(wget -qO- https://raw.githubusercontent.com/Sowevo/my_script/main/shell/auto-generate-docker-tls-ca.sh)"
#   sh -c "$(wget -qO- https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/auto-generate-docker-tls-ca.sh)"
# or via fetch:
#   sh -c "$(fetch -o - https://raw.githubusercontent.com/Sowevo/my_script/main/shell/auto-generate-docker-tls-ca.sh)"
#   sh -c "$(fetch -o - https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/auto-generate-docker-tls-ca.sh)"

# 服务器主机名
SERVER="172.16.20.126"
# 密码
PASSWORD="Super#Geostar,5"
# 国家
COUNTRY="CN"
# 省份
STATE="北京市"
# 城市
CITY="北京市"
# 机构名称
ORGANIZATION="大白兔技术股份有限公司"
# 机构单位
ORGANIZATIONAL_UNIT="大白兔技术股份有限公司"
# 邮箱
EMAIL="x@sowevo.com"

# 生成CA密钥
openssl genrsa -aes256 -passout pass:$PASSWORD  -out ca-key.pem 2048

# 生成CA证书
openssl req -utf8 -new -x509 -passin "pass:$PASSWORD" -days 3650 -key ca-key.pem -sha256 -out ca-cert.pem -subj "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORGANIZATION/OU=$ORGANIZATIONAL_UNIT/CN=$SERVER/emailAddress=$EMAIL"

# 生成服务端密钥
openssl genrsa -out server-key.pem 2048

# 生成服务端证书签名的请求文件
openssl req -subj "/CN=$SERVER" -new -key server-key.pem -out server-req.csr

# 生成服务端证书
openssl x509 -req -days 3650 -in server-req.csr -CA ca-cert.pem -CAkey ca-key.pem -passin "pass:$PASSWORD" -CAcreateserial -out server-cert.pem

# 生成客户端密钥
openssl genrsa -out client-key.pem 2048

# 生成客户端证书签名的请求文件
openssl req -subj '/CN=client' -new -key client-key.pem -out client-req.csr

# 生成客户端证书
sh -c 'echo "extendedKeyUsage=clientAuth" >> extfile.cnf'
openssl x509 -req -days 3650 -in client-req.csr -CA ca-cert.pem -CAkey ca-key.pem  -passin "pass:$PASSWORD" -CAcreateserial -out client-cert.pem -extfile extfile.cnf

# 更改密钥权限
chmod 0400 ca-key.pem server-key.pem client-key.pem
# 更改证书权限
chmod 0444 ca-cert.pem server-cert.pem client-cert.pem
# 删除无用文件
# rm ca-cert.srl client-req.csr server-req.csr extfile.cnf
