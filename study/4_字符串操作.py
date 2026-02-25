# name = input("请输入名字: ")
# address = input("请输入地址: ")
# age = int(input("请输入年龄: "))
# hobby = input("请输入爱好: ")


# # %s 字符串, 占位符
# # %d 整数, 占位符
# # %f 小数, 占位符
# s = "我是%s, 住在%s, 今年%d岁, 我喜欢%s" % (name, address, age, hobby)
# s1 = "我是{}, 住在{}, 今年{}岁, 我喜欢{}".format(name, address, age, hobby)
# s2 = f"我是{name}, 住在{address}, 今年{age}岁, 我喜欢{hobby}" # f-string  v3.5后支持

# print(s)
# print(s1) 
# print(s2) 



# s = "我是唐清伟"

# 索引提取
# print(s[2])
# print(s[-1])


# # 切片
# print(s[1:3])
# print(s[:3])
# print(s[3:])
# print(s[:])
# print(s[-3:-1])
# print(s[-1:-3]) # 只能从左往右切
# print(type(s[1:3]))


# # 切片方向
# print(s[::-1]) # 反转 

# # s[start:end:step]
# print(s[0::2]) # 步长切片


# s = "    i have a dReam!    "

# # 单词首字母大写
# # print(s.title())

# # 首字母大写 
# print(s.capitalize())

# # 全小写
# print(s.lower()) 

# # 全大写
# print(s.upper())

# # 去掉左右两端空白符(空格, \n, \t)
# print(s.strip())

# # 替换
# print(s.replace(' ',''))

# # 切割 split(切割符)
# print(s.strip().split(' '), type(s.strip().split(' ')))

s = "12345"

# 查找, 返回 index, 返回-1等于没有
# print(n.find('0')) 

# 查找, 不匹配直接报错
# print(s.index("0"))

# 是否存在, 返回布尔值
print("0" in s)