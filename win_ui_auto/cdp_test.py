from playwright.sync_api import sync_playwright


def connect_ideal():
    with sync_playwright() as p:
        print("[*] 正在通过 CDP 连接 iDeal.exe (端口 9222)...")
        try:
            # 连接到已经开启 9222 端口的 iDeal 浏览器实例
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")

            # 获取当前所有的上下文和页面 (iDeal 可能有多个面板，每个面板是一个 page)
            contexts = browser.contexts
            if not contexts:
                print("[-] 未找到浏览器上下文")
                return

            page = contexts[0].pages[0]
            print(f"[+] 成功连接！当前页面标题: {page.title()}")
            print(f"[+] 当前页面 URL: {page.url}")

            # 打印页面的完整 HTML 源码 (验证是否抓到了真实的内部元素)
            print("================ 页面 HTML 前 500 个字符 ================")
            print(page.content()[:500])
            print("=========================================================")

            # 示例：你可以直接用真实的 Web XPath 或 CSS 选择器去点击/获取文本了！
            # buttons = page.locator('//button').all()
            # for btn in buttons:
            #     print(btn.text_content())

            # 保持连接不立即关闭（用于观察）
            input("按回车键断开连接退出...")

        except Exception as e:
            print(f"[-] 连接失败: {e}")
            print("请确认 iDeal.exe 确实以 --remote-debugging-port=9222 启动，且端口未被占用。")


if __name__ == "__main__":
    connect_ideal()