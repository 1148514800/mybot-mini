# timezone-day-001

修复UTC报表日期：有offset的ISO时间必须先转换UTC；无时区按UTC，支持Z。保留跨月、跨年和闰日边界。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
