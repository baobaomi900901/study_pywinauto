a = -1
if a > 1:
  print('a')
  pass
else:
  print('b')
  pass 


b = input('钞票有多少:')

if int(b) > 500:
  print('富哥')
  pass
elif int(b) > 250:
  print('打工仔')
  pass
else:
  print('穷逼')
  pass

c = input('周几:')

def switch_example(value):
  match int(c):
      case 1:
          return "星期一"
      case 2:
          return "星期二"
      case 3:
          return "星期三"
      case _:
          return "其他"

print(switch_example(c))