# Public Tests

工作区tests/test_search.py包含5个真实业务测试：title匹配、body匹配、大小写无关、纯空白查询、输入原始顺序。源码为可信资产，在fixture.py中构造并由hash冻结；不允许模型改断言。只用标准库unittest，不安装第三方包。

唯一允许测试argv为python -m unittest discover -s tests -v，cwd为根目录'.'，超时不超过30秒。RunCommand将其解析为受验证的绝对Python路径；WebApproval必须显示完整有效argv/cwd/模式/超时，由真人在Live逐次确认。模型请求授权不能代替该批准。

原Bug至少有一项真实失败，Reference修复全部通过。原生测试成功可支持当前Revision Controller证据，但不能替代Host Acceptance，也不能证明整个项目所有行为正确。测试输出可返回Agent作为ReAct反馈；Host隐藏结果永不返回模型。
