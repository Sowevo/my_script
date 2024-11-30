import os
import re
"""
115的文件重命名的csv生成的脚本
"""

file_name = "/Users/sowevo/Downloads/kn.txt"

# 正则表达式模式：提取数字（包括小数）
pattern_number = r"(\d+(\.\d+)?)"

# 设定字符模式
pattern_format = "名侦探柯南 - S01E# - 第@集"

# 读取文件
with open(file_name, "r") as file:
    for line in file:
        line = line.strip()  # 去除行首尾空白字符

        # 提取文件后缀
        _, file_extension = os.path.splitext(line)  # 获取文件后缀

        # 使用正则表达式提取数字
        number_match = re.search(pattern_number, line)

        if number_match:
            number = number_match.group(0)  # 提取数字部分

            # 判断数字是整数还是小数
            if '.' in number:  # 小数
                integer_part, decimal_part = number.split('.')  # 分割整数和小数部分
                # 整数部分补零2位，小数部分不动
                formatted_number = f"{int(integer_part):02d}.{decimal_part}"
            else:  # 整数
                formatted_number = f"{int(number):02d}"  # 整数部分补零2位

            # 构建最终格式化的字符串
            formatted_str = pattern_format.replace('#', formatted_number)  # #替换为格式化后的数字
            formatted_str = formatted_str.replace('@', number)  # @替换为原始数字
            formatted_str += file_extension  # 拼接文件后缀
            print(f'{line},{formatted_str}')
