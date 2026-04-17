# win_ui_auto/hooks/el_if.py
import sys
import uiautomation as auto
from hooks.locator import locate_by_xpath

def run(xpath, timeout=10.0):
    """
    判断控件是否存在且有效。
    逻辑：
    1. 调用统一的 locate_by_xpath 进行寻址。
    2. 如果返回 None，判定为不存在。
    3. 如果找到控件，验证其物理面积（BoundingRectangle），防止抓到已销毁的幽灵节点。
    """
    try:
        # 必须在线程初始化环境下操作 UIA
        with auto.UIAutomationInitializerInThread():
            # 直接调用你 locator.py 里的神级寻路逻辑
            el = locate_by_xpath(xpath, timeout=timeout)

            if el:
                # 强制刷新一次，避免拿到 UIA 缓存的“幽灵对象”
                try:
                    el.Refresh()
                except Exception:
                    pass

                # 进一步验证：必须“存在 + 有物理尺寸”
                # 说明：
                # - 仅靠 locate_by_xpath 可能拿到 UIA 缓存对象；这里用 Exists 做二次确认
                # - IsOffscreen 在 CEF/MSAA 场景很容易误判（窗口不前台、被遮挡、渲染策略等），不作为否定条件
                try:
                    if not el.Exists(0.8, 0.1):
                        print("False")
                        return False
                except Exception:
                    # Exists 异常时不作为直接失败条件，继续用 BoundingRectangle 判断
                    pass

                rect = None
                try:
                    rect = el.BoundingRectangle
                except Exception:
                    rect = None

                if rect and rect.width() > 0 and rect.height() > 0:
                    print("True")
                    return True
            
            # 走到这里说明定位失败或控件无效
            print("False")
            return False
            
    except Exception:
        # 任何异常（如 COM 错误）统一视为不存在
        print("False")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="判断元素是否存在")
    parser.add_argument("xpath", type=str, help="目标 XPath")
    parser.add_argument("--timeout", type=float, default=10.0, help="超时时间")
    args = parser.parse_args()
    
    run(args.xpath, args.timeout)

if __name__ == "__main__":
    main()