import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, List, Callable, Any, Optional

# ==================== 配置区域 ====================
# 定义每个字段的提取规则
# 支持以下几种提取方式：
#   - selector: CSS 选择器（优先级最高）
#   - tag: HTML 标签名，配合 class/attrs 使用
#   - class: 类名（单个字符串或多个类名的列表）
#   - attrs: 要获取的属性，默认为 "text" 表示获取文本内容
#   - transform: 可选函数，对提取的值进行转换（如拼接绝对 URL）

# ==================== 提取函数 ====================
def extract_field(article: BeautifulSoup, field_rule: Dict[str, Any]) -> Any:
    """
    根据规则从单个商品块中提取指定字段的值
    """
    # 1. 确定搜索范围（默认为 article 本身）
    target = article

    # 如果规则包含 selector，直接使用 CSS 选择器
    if "selector" in field_rule:
        elem = article.select_one(field_rule["selector"])
        if not elem:
            return None
        target = elem
    else:
        # 根据 tag 和 class 进行查找
        tag = field_rule.get("tag")
        class_name = field_rule.get("class")
        find_tag = field_rule.get("find")  # 可选：在找到的元素内再查找

        if class_name:
            # 支持多个类名
            if isinstance(class_name, list):
                class_str = " ".join(class_name)
            else:
                class_str = class_name
            elem = article.find(tag, class_=class_str) if tag else article.find(class_=class_str)
        elif tag:
            elem = article.find(tag)
        else:
            elem = article

        if not elem:
            return None

        # 如果指定了 find，则在 elem 内继续查找
        if find_tag:
            if isinstance(find_tag, str):
                elem = elem.find(find_tag)
            elif isinstance(find_tag, dict):
                elem = elem.find(**find_tag)
            if not elem:
                return None
        target = elem

    # 2. 获取值
    attr = field_rule.get("attrs", "text")
    if attr == "text":
        value = target.get_text(strip=False)
    else:
        value = target.get(attr)

    # 3. 应用转换函数（如果有）
    transform = field_rule.get("transform")
    if transform and value is not None:
        value = transform(value)

    return value

def extract_item(article: BeautifulSoup, config: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    根据配置从单个商品块中提取所有字段
    """
    item = {}
    for field_name, rule in config.items():
        item[field_name] = extract_field(article, rule)
    return item

# ==================== 分页抓取函数 ====================
def scrape_books(start_page: int = 1, total_pages: int = 1, config: Dict = None) -> List[Dict[str, Any]]:
    """
    抓取书籍信息，支持分页和自定义字段配置
    """
    if config is None:
        config = ITEM_CONFIG

    base_url = "http://books.toscrape.com/catalogue/page-{}.html"
    all_books = []
    end_page = start_page + total_pages - 1

    for page_num in range(start_page, end_page + 1):
        print(f"正在抓取第 {page_num} 页...")
        try:
            url = base_url.format(page_num)
            response = requests.get(url)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, "html.parser")

            articles = soup.find_all("article", class_="product_pod")
            if not articles:
                print(f"第 {page_num} 页无数据，停止抓取。")
                break

            for article in articles:
                item = extract_item(article, config)
                all_books.append(item)

        except requests.RequestException as e:
            print(f"抓取第 {page_num} 页时出错: {e}")
            break

    return all_books

# ==================== 主程序 ====================
if __name__ == "__main__":
    START_PAGE = 1
    TOTAL_PAGES = 3

    ITEM_CONFIG: Dict[str, Dict[str, Any]] = {
      "物品名字": {
          "tag": "h3",
          "find": "a",          # 在 h3 内进一步查找 a 标签
          "attrs": "title",     # 获取 title 属性
          "transform": lambda x: x.strip() if x else ""
      },
      "价格": {
          "class": "price_color",
          "tag": "p",
          "attrs": "text",      # 获取文本内容
          "transform": lambda x: x.strip() if x else ""
      },
      "图片地址": {
          "class": "image_container",
          "tag": "img",
          "attrs": "src",       # 获取 src 属性
          "transform": lambda src: (
              "http://books.toscrape.com/" + src[3:] if src.startswith("../media/")
              else ("http://books.toscrape.com/" + src if src.startswith("media/")
                    else src)
          )
      },
      # 示例：添加库存状态字段（可选）
      # "库存": {
      #     "class": "instock availability",
      #     "tag": "p",
      #     "attrs": "text",
      #     "transform": lambda x: x.strip() if x else ""
      # }
    }

    books = scrape_books(start_page=START_PAGE, total_pages=TOTAL_PAGES, config=ITEM_CONFIG)

    print(json.dumps(books, ensure_ascii=False, indent=2))
    print(f"\n共抓取到 {len(books)} 本书籍信息。")