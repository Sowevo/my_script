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


# 需要自己更改下以下配置
# 服务器主机名
SERVER="10.0.8.11"
# 密码
PASSWORD="Super#Geostar,5"
# 国家
COUNTRY="CN"
# /etc/pki/tls/openssl.cnf，即 openssl 的配置文件路径并不一定适合所有系统
# 可以使用 find 命令找出自己系统中 openssl.cnf 的位置：
OPENSSL_CONF="/etc/pki/tls/openssl.cnf"
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
openssl genrsa -aes256 -passout pass:$PASSWORD  -out ca-key.pem 4096

# 生成CA证书
openssl req -utf8 -new -x509 -passin "pass:$PASSWORD" -days 3650 -key ca-key.pem -sha256 -out ca-cert.pem -subj "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORGANIZATION/OU=$ORGANIZATIONAL_UNIT/CN=$SERVER/emailAddress=$EMAIL"

# 生成服务端密钥
openssl genrsa -out server-key.pem 4096

# 生成服务端证书签名的请求文件
openssl req -subj "/CN=$SERVER" -new -key server-key.pem -out server-req.csr -reqexts SAN -config <(cat $OPENSSL_CONF <(printf "\n[SAN]\nsubjectAltName=IP:$SERVER"))

# 生成服务端证书
openssl x509 -req -days 3650 -in server-req.csr -CA ca-cert.pem -CAkey ca-key.pem -passin "pass:$PASSWORD" -CAcreateserial -out server-cert.pem -extensions SAN -extfile <(cat $OPENSSL_CONF <(printf "[SAN]\nsubjectAltName=IP:$SERVER"))

# 生成客户端密钥
openssl genrsa -out client-key.pem 4096

# 生成客户端证书签名的请求文件
openssl req -subj '/CN=client' -new -key client-key.pem -out client-req.csr

# 生成客户端证书
sh -c 'echo "extendedKeyUsage=clientAuth" >> extfile.cnf'
openssl x509 -req -days 3650 -in client-req.csr -CA ca-cert.pem -CAkey ca-key.pem  -passin "pass:$PASSWORD" -CAcreateserial -out client-cert.pem -extfile extfile.cnf

# 更改密钥权限
chmod 0400 ca-key.pem server-key.pem client-key.pem
# 更改证书权限
chmod 0444 ca-cert.pem server-cert.pem client-cert.pem