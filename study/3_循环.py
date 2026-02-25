# num = 0

# while num < 10:
#   print(num)
#   num = num + 1



# 累加 1+2+3...100

# i = 1
# s = 0

# while i <= 3:
#   s = i + s
#   i = i+1

#   print("@",s)
  
#   if i > 3:
#     print(i)
#     print(s)


# break : 结束循环
# continue : 结束本次循环, 执行下一次循环




# for i in 'abc':
#   print(i)


# for i in [1,2,3]:
#   print(i)


# range(n) 不包含n
# range(m,n) 从m开始, 保护m, 不包含n
# range(m,n,s) 从m开始, 保护m, 不包含n, 每次间隔s
for i in range(0,10,2):
  print(i)