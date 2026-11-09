# 仓库开发规则

## 仓库结构与依赖

| 路径 | 职责 |
| --- | --- |
| `src/main/kotlin/` | Kotlin/JVM 协议库，负责编解码、命令构造和响应解析。蓝牙连接由调用方管理。 |
| `src/test/kotlin/` | Kotlin 协议和帧处理测试。 |
| `tools/webtest.py` | Python 本地调试面板、串口传输和模拟设备。运行依赖由 `requirements.txt` 管理，HTTP 服务使用 Python 标准库。 |
| `tools/test_webtest.py` | 使用 pytest 和模拟串口验证 Web 面板的协议行为。 |
| `docs/` | 协议参考、逆向记录与 Web API 文档。 |

- 遵循 `.editorconfig` 与现有代码风格。共享协议规则变更时，检查 Kotlin 和 Python 两端的实现、测试及 `docs/PROTOCOL.md` 是否一致。
- 项目版本按「年.大版本.构建次数」管理，只在 `version.properties` 中维护。普通发布递增末段，大版本升级递增中段并将末段归一，跨年从新年份的 `1.1` 起步。日常构建不改版本，依赖和协议版本独立维护。
- 保留 Gradle Wrapper。代理和本机路径放在各自的环境配置中。抓包、APK、反编译产物和本地交接文件按 `.gitignore` 管理。

## 协议和面板约束

- 区分匹配的成功响应、匹配的设备拒绝、无关通知和超时。设备拒绝可作为在线证据，操作成功仍由对应命令的结果判定。
- 串口收发、重试和共享接收缓冲区使用同一个命令锁。只对确认幂等的查询启用自动重发，写入失败优先于读回值一致。
- Web 面板只监听回环地址。写接口继续校验请求来源，修改整包设置时保留已读到的未编辑字段。
- 新增或修正协议结论时，注明依据是 APK、抓包、模拟还是特定固件真机。涉及帧格式和命令编号时先读 `docs/PROTOCOL.md`，再核对源码和相应用例。

## 验证

- Kotlin 协议改动使用 JDK 17 和 Gradle Wrapper 执行 `./gradlew test`。变更构建配置、依赖或产物时执行 `./gradlew build`。Windows 使用 `gradlew.bat`。
- Web 面板改动先安装 `requirements.txt` 和 pytest，再执行 `python -m pytest -q tools/test_webtest.py`。改动串口或写入路径时按需要覆盖普通 DEMO、无 ACK 和延迟模式。
- 文档和忽略规则的小改动检查链接、`git diff --check` 及适用的 `git check-ignore`，无需编译。验证报告分别注明自动化、模拟与真机验证范围。
