# 浏览器身份隔离检查

结论：**所需隔离未获证明，Case启动前BLOCKED**。不是因为旧MyBot进程存在。

## 能力与实测

当前工具提供Chrome extension、内置IAB和MCP Apps。只读枚举IAB browser capabilities为visibility/viewport；Chrome为viewport/management。Chrome management文档明确只支持normal、non-incognito窗口；标签API没有userDataDir、createContext或独立Cookie Jar参数。sessionName是会话名，不作为配置文件隔离证据。没有尝试被禁止的incognito参数、修改生产Cookie或通过其他驱动绕过限制。

为避免仅凭API缺失推断，运行了独立非生产HTTP页面127.0.0.1:8896，用IAB自己的两个新标签作探针：

| 步骤 | 专用测试Cookie存在 | 专用LocalStorage标记存在 |
|---|---|---|
| 标签A初始 | false | false |
| 在A点击写测试标记 | true | true |
| 新建标签B同源 | true | true |
| 在B移除专用标记，A重载 | false | false |

实测证明IAB新标签共享Cookie和LocalStorage，不能以“新标签”充当新身份。这不证明IAB与用户Chrome共享存储；没有访问原Chrome的Cookie或做该对照，因此不能据此声称已发生用户Cookie冲突。也不能仅因provider名称不同就宣称已满足“全新独立临时配置/真正隔离上下文”的要求。

专用Cookie名称不是mybot_browser；只创建/清理自己的无凭证测试标记，没有读取/修改原用户Chrome配置、8765页面、mybot_browser、Cookie或LocalStorage。测试脚本在/tmp，未进入冻结源码/工作区。两个测试标签已关闭，8896探针服务收到Ctrl-C正常结束，端口释放；没有关闭任何用户浏览器进程。

截图browser-probe-shared-storage.png为标签B真实观察；browser-probe-cleaned.png为清理后A重载，均只含非生产布尔值，不是Live UAT截图或成绩。

## 缺少的能力

需要浏览器工具提供可控制的新临时user-data-dir/profile，或可创建/销毁独立BrowserContext，明确独立Cookie Jar与LocalStorage，并允许在两个受控测试身份上做本地验证。没有此能力，不启动L01来碰运气，也不把不同端口、普通窗口或不同标签当作隔离。
