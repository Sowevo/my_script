# 用来根据参数生成ss:// ssr:// 的链接
Green_font_prefix="\033[32m" && Red_font_prefix="\033[31m" && Green_background_prefix="\033[42;37m" && Red_background_prefix="\033[41;37m" && Font_color_suffix="\033[0m"
# 判断系统
check_sys(){
	if [[ -f /etc/redhat-release ]]; then
		release="centos"
	elif cat /etc/issue | grep -q -E -i "debian"; then
		release="debian"
	elif cat /etc/issue | grep -q -E -i "ubuntu"; then
		release="ubuntu"
	elif cat /etc/issue | grep -q -E -i "centos|red hat|redhat"; then
		release="centos"
	elif cat /proc/version | grep -q -E -i "debian"; then
		release="debian"
	elif cat /proc/version | grep -q -E -i "ubuntu"; then
		release="ubuntu"
	elif cat /proc/version | grep -q -E -i "centos|red hat|redhat"; then
		release="centos"
    fi
	bit=`uname -m`
}
urlsafe_base64(){
	date=$(echo -n "$1"|base64|sed ':a;N;s/\n/ /g;ta'|sed 's/ //g;s/=//g;s/+/-/g;s/\//_/g')
	echo -e "${date}"
}
urlencode(){
    date=$(echo "$1"| tr -d '\n' | xxd -plain | sed 's/\(..\)/%\1/g')
	echo -e "${date}"
}
ss_link_qr(){
    SSRemarks=$(urlencode "${remarks}")
	SSbase64=$(urlsafe_base64 "${method}:${password}@${ip}:${port}")
	SSurl="ss://${SSbase64}#${SSRemarks}"
	ss_link=" SS    链接 : ${Green_font_prefix}${SSurl}${Font_color_suffix} \n"
}
ssr_link_qr(){
	SSRprotocol=$(echo ${protocol} | sed 's/_compatible//g')
	SSRobfs=$(echo ${obfs} | sed 's/_compatible//g')
	SSRPWDbase64=$(urlsafe_base64 "${password}")
    SSRRemarksbase64=$(urlsafe_base64 "${remarks}")
	SSRbase64=$(urlsafe_base64 "${ip}:${port}:${SSRprotocol}:${method}:${SSRobfs}:${SSRPWDbase64}?remarks=${SSRRemarksbase64}")
	SSRurl="ssr://${SSRbase64}"
	ssr_link=" SSR   链接 : ${Red_font_prefix}${SSRurl}${Font_color_suffix} \n"
}
ss_ssr_determine(){
	protocol_suffix=`echo ${protocol} | awk -F "_" '{print $NF}'`
	obfs_suffix=`echo ${obfs} | awk -F "_" '{print $NF}'`
	if [[ ${protocol} = "origin" ]]; then
		if [[ ${obfs} = "plain" ]]; then
			ss_link_qr
			ssr_link=""
		else
			if [[ ${obfs_suffix} != "compatible" ]]; then
				ss_link=""
			else
				ss_link_qr
			fi
		fi
	else
		if [[ ${protocol_suffix} != "compatible" ]]; then
			ss_link=""
		else
			if [[ ${obfs_suffix} != "compatible" ]]; then
				if [[ ${obfs_suffix} = "plain" ]]; then
					ss_link_qr
				else
					ss_link=""
				fi
			else
				ss_link_qr
			fi
		fi
	fi
	ssr_link_qr
}
View_User(){
    ss_ssr_determine
    clear && echo "===================================================" && echo
		echo -e " ShadowsocksR账号 配置信息：" && echo
		echo -e " I  P\t    : ${Green_font_prefix}${ip}${Font_color_suffix}"
		echo -e " 端口\t    : ${Green_font_prefix}${port}${Font_color_suffix}"
		echo -e " 密码\t    : ${Green_font_prefix}${password}${Font_color_suffix}"
		echo -e " 加密\t    : ${Green_font_prefix}${method}${Font_color_suffix}"
		echo -e " 协议\t    : ${Red_font_prefix}${protocol}${Font_color_suffix}"
		echo -e " 混淆\t    : ${Red_font_prefix}${obfs}${Font_color_suffix}"
		echo -e "${ss_link}"
		echo -e "${ssr_link}"
		echo -e " ${Green_font_prefix} 提示: ${Font_color_suffix}
在浏览器中，打开二维码链接，就可以看到二维码图片。
协议和混淆后面的[ _compatible ]，指的是 兼容原版协议/混淆。"
		echo && echo "==================================================="
}
# 设置 配置信息
Set_config_all(){
    Set_config_ip
	Set_config_port
    Set_config_remarks
	Set_config_password
	Set_config_method
	Set_config_protocol
	Set_config_obfs
}

Set_config_port(){
	while true
	do
	echo -e "请输入您的ShadowsocksR 端口"
	read -e -p "(默认: 2333):" port
	[[ -z "$port" ]] && port="2333"
	echo $((${port}+0)) &>/dev/null
	if [[ $? == 0 ]]; then
		if [[ ${port} -ge 1 ]] && [[ ${port} -le 65535 ]]; then
			echo && echo ${Separator_1} && echo -e "	端口 : ${Green_font_prefix}${port}${Font_color_suffix}" && echo ${Separator_1} && echo
			break
		else
			echo -e "${Error} 请输入正确的数字(1-65535)"
		fi
	else
		echo -e "${Error} 请输入正确的数字(1-65535)"
	fi
	done
}

Set_config_password(){
	echo "请输入您的ShadowsocksR 密码"
	read -e -p "(默认: baidu.com):" password
	[[ -z "${password}" ]] && password="baidu.com"
	echo && echo ${Separator_1} && echo -e "	密码 : ${Green_font_prefix}${password}${Font_color_suffix}" && echo ${Separator_1} && echo
}

Set_config_remarks(){
	echo "请输入您的ShadowsocksR 备注"
	read -e -p "(默认: 新节点):" remarks
	[[ -z "${remarks}" ]] && remarks="新节点"
	echo && echo ${Separator_1} && echo -e "	备注 : ${Green_font_prefix}${remarks}${Font_color_suffix}" && echo ${Separator_1} && echo
}

Set_config_ip(){
	echo "请输入您的ShadowsocksR IP/域名"
	read -e -p "(默认: baidu.com):" ip
	[[ -z "${ip}" ]] && ip="baidu.com"
	echo && echo ${Separator_1} && echo -e "	IP/域名 : ${Green_font_prefix}${ip}${Font_color_suffix}" && echo ${Separator_1} && echo
}

Set_config_method(){
	echo -e "请选择您的ShadowsocksR 加密方式

 ${Green_font_prefix} 1.${Font_color_suffix} none

 ${Green_font_prefix} 2.${Font_color_suffix} rc4
 ${Green_font_prefix} 3.${Font_color_suffix} rc4-md5
 ${Green_font_prefix} 4.${Font_color_suffix} rc4-md5-6

 ${Green_font_prefix} 5.${Font_color_suffix} aes-128-ctr
 ${Green_font_prefix} 6.${Font_color_suffix} aes-192-ctr
 ${Green_font_prefix} 7.${Font_color_suffix} aes-256-ctr

 ${Green_font_prefix} 8.${Font_color_suffix} aes-128-cfb
 ${Green_font_prefix} 9.${Font_color_suffix} aes-192-cfb
 ${Green_font_prefix}10.${Font_color_suffix} aes-256-cfb

 ${Green_font_prefix}11.${Font_color_suffix} aes-128-cfb8
 ${Green_font_prefix}12.${Font_color_suffix} aes-192-cfb8
 ${Green_font_prefix}13.${Font_color_suffix} aes-256-cfb8

 ${Green_font_prefix}14.${Font_color_suffix} salsa20
 ${Green_font_prefix}15.${Font_color_suffix} chacha20
 ${Green_font_prefix}16.${Font_color_suffix} chacha20-ietf" && echo
	read -e -p "(默认: 5. aes-128-ctr):" method
	[[ -z "${method}" ]] && method="5"
	if [[ ${method} == "1" ]]; then
		method="none"
	elif [[ ${method} == "2" ]]; then
		method="rc4"
	elif [[ ${method} == "3" ]]; then
		method="rc4-md5"
	elif [[ ${method} == "4" ]]; then
		method="rc4-md5-6"
	elif [[ ${method} == "5" ]]; then
		method="aes-128-ctr"
	elif [[ ${method} == "6" ]]; then
		method="aes-192-ctr"
	elif [[ ${method} == "7" ]]; then
		method="aes-256-ctr"
	elif [[ ${method} == "8" ]]; then
		method="aes-128-cfb"
	elif [[ ${method} == "9" ]]; then
		method="aes-192-cfb"
	elif [[ ${method} == "10" ]]; then
		method="aes-256-cfb"
	elif [[ ${method} == "11" ]]; then
		method="aes-128-cfb8"
	elif [[ ${method} == "12" ]]; then
		method="aes-192-cfb8"
	elif [[ ${method} == "13" ]]; then
		method="aes-256-cfb8"
	elif [[ ${method} == "14" ]]; then
		method="salsa20"
	elif [[ ${method} == "15" ]]; then
		method="chacha20"
	elif [[ ${method} == "16" ]]; then
		method="chacha20-ietf"
	else
		method="aes-128-ctr"
	fi
	echo && echo ${Separator_1} && echo -e "	加密 : ${Green_font_prefix}${method}${Font_color_suffix}" && echo ${Separator_1} && echo
}
Set_config_protocol(){
	echo -e "请选择您的ShadowsocksR 协议插件

 ${Green_font_prefix}1.${Font_color_suffix} origin
 ${Green_font_prefix}2.${Font_color_suffix} auth_sha1_v4
 ${Green_font_prefix}3.${Font_color_suffix} auth_aes128_md5
 ${Green_font_prefix}4.${Font_color_suffix} auth_aes128_sha1
 ${Green_font_prefix}5.${Font_color_suffix} auth_chain_a
 ${Green_font_prefix}6.${Font_color_suffix} auth_chain_b" && echo
	read -e -p "(默认: 2. auth_sha1_v4):" protocol
	[[ -z "${protocol}" ]] && protocol="2"
	if [[ ${protocol} == "1" ]]; then
		protocol="origin"
	elif [[ ${protocol} == "2" ]]; then
		protocol="auth_sha1_v4"
	elif [[ ${protocol} == "3" ]]; then
		protocol="auth_aes128_md5"
	elif [[ ${protocol} == "4" ]]; then
		protocol="auth_aes128_sha1"
	elif [[ ${protocol} == "5" ]]; then
		protocol="auth_chain_a"
	elif [[ ${protocol} == "6" ]]; then
		protocol="auth_chain_b"
	else
		protocol="auth_sha1_v4"
	fi
	echo && echo ${Separator_1} && echo -e "	协议 : ${Green_font_prefix}${protocol}${Font_color_suffix}" && echo ${Separator_1} && echo
}
Set_config_obfs(){
	echo -e "请选择您的ShadowsocksR 混淆插件

 ${Green_font_prefix}1.${Font_color_suffix} plain
 ${Green_font_prefix}2.${Font_color_suffix} http_simple
 ${Green_font_prefix}3.${Font_color_suffix} http_post
 ${Green_font_prefix}4.${Font_color_suffix} random_head
 ${Green_font_prefix}5.${Font_color_suffix} tls1.2_ticket_auth" && echo
	read -e -p "(默认: 1. plain):" obfs
	[[ -z "${obfs}" ]] && obfs="1"
	if [[ ${obfs} == "1" ]]; then
		obfs="plain"
	elif [[ ${obfs} == "2" ]]; then
		obfs="http_simple"
	elif [[ ${obfs} == "3" ]]; then
		obfs="http_post"
	elif [[ ${obfs} == "4" ]]; then
		obfs="random_head"
	elif [[ ${obfs} == "5" ]]; then
		obfs="tls1.2_ticket_auth"
	else
		obfs="plain"
	fi
	echo && echo ${Separator_1} && echo -e "	混淆 : ${Green_font_prefix}${obfs}${Font_color_suffix}" && echo ${Separator_1} && echo
}




check_sys
[[ ${release} != "debian" ]] && [[ ${release} != "ubuntu" ]] && [[ ${release} != "centos" ]] && echo -e "${Error} 本脚本不支持当前系统 ${release} !" && exit 1
Set_config_all
View_User