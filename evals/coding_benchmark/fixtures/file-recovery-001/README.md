# file-recovery-001

修复保存文本失败后原文件被截断的问题：参数类型或UTF8编码失败必须保持旧字节；成功安全替换，不遗留临时文件。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
