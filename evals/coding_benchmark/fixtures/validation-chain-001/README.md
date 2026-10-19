# validation-chain-001

输入为字符串。修复注册链路：先strip/lower规范化邮箱，再验证仅一个@、非空用户名、含点域名且无空白；返回规范化邮箱，非法输入抛ValueError。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
