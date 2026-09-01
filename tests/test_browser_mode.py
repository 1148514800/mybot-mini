import unittest

from mybot.agent.context import (
    BROWSER_MODE_LOCAL,
    BROWSER_MODE_MANAGED,
    ContextBuilder,
)


class BrowserModeTests(unittest.TestCase):
    def test_unspecified_browser_requests_default_to_managed(self) -> None:
        messages = (
            "打开 B 站",
            "搜索奶龙并播放第五个视频",
            "open bilibili",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(
                    ContextBuilder.resolve_browser_mode(message),
                    BROWSER_MODE_MANAGED,
                )

    def test_explicit_local_browser_requests_use_local(self) -> None:
        messages = (
            "使用本地浏览器打开 B 站",
            "操作当前 Chrome",
            "连接已经打开的浏览器",
            "use my existing browser",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(
                    ContextBuilder.resolve_browser_mode(message),
                    BROWSER_MODE_LOCAL,
                )

    def test_explicit_managed_browser_requests_use_managed(self) -> None:
        messages = (
            "打开一个新浏览器",
            "使用托管浏览器访问网站",
            "open a separate browser",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(
                    ContextBuilder.resolve_browser_mode(message),
                    BROWSER_MODE_MANAGED,
                )

    def test_negated_mode_requests_choose_the_opposite_mode(self) -> None:
        self.assertEqual(
            ContextBuilder.resolve_browser_mode("不要打开新浏览器"),
            BROWSER_MODE_LOCAL,
        )
        self.assertEqual(
            ContextBuilder.resolve_browser_mode("不要使用本地浏览器"),
            BROWSER_MODE_MANAGED,
        )


if __name__ == "__main__":
    unittest.main()
