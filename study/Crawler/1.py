import requests

head = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; X64)"
}
# res = requests.get("https://www.baidu.com")
res = requests.get("http://books.toscrape.com/", headers = head)
res.encoding = res.apparent_encoding  # apparent_encoding 基于内容分析得出真实编码

print(res)

if res.ok:
  print("请求成功")
  print(res.text)
else:
  print("请求失败")