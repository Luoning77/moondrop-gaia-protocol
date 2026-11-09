# PR #1 复审与验证

[PR #1](https://github.com/Luoning77/moondrop-gaia-protocol/pull/1) 的首轮五项修复、构建输出和固件 3.5.6 真机记录保存在 [393a9bf 的验证报告](https://github.com/XEDAB/moondrop-gaia-protocol/blob/393a9bf0cda57f61f20de939bce569fb66862b31/docs/PR_%E4%BF%AE%E5%A4%8D%E4%B8%8E%E9%AA%8C%E8%AF%81%E6%8A%A5%E5%91%8A.md)。本页记录该提交之后的本地复审。

| 复审项 | 修复与验证 |
| --- | --- |
| 错误帧、探活和刷新状态 | 探活只接受与请求匹配的应答，匹配的拒绝帧只作为在线证据。回归测试覆盖不匹配的固件应答、仅有通知、设备拒绝和串口写失败。读取中断时保留已读字段，页面提示重新读取并锁定控制项。 |
| 收帧与重同步 | 优先按声明长度接收完整帧，超时仍未收全时尝试恢复后续完整帧。测试覆盖 payload 含帧形字节，以及坏长度后直接收到有效帧、先收到通知再收到有效帧。 |
| 并发与重试 | 同一命令持锁至重试结束，双线程测试覆盖通知和匹配响应同批到达的情况。`/api/send` 只重试已知幂等查询。测试确认 EQ 写入、保存、NV ID 和翻页命令各发一次。 |

## 验证环境与结果

- macOS / Python 3.9.6，运行 `python -m pytest -q tools/test_webtest.py`，50 项通过。
- 本机 HTTP 验证覆盖普通 DEMO、无 ACK DEMO 和 0.1 秒延迟 DEMO。每种模式均读到 13 项状态，增益写入并读回正确，不支持的命令返回 `device_error`。另用 Node 执行页面的 `refreshAll()`，检查正常刷新与中途断连的提示及控制状态。
- 本轮修改前，当前工作区的 Gradle 9.4.1 / JDK 17 构建已通过，50 项 Kotlin 测试通过，并生成 `moondrop-pudding-protocol-26.1.1.jar`。验证使用临时 Maven 镜像配置，本轮修改只涉及 Web 面板、其测试和文档。
- 本轮未复测 Windows SPP 真机。协议没有校验和，若损坏长度恰好构成一个完整外帧，接收器会按声明长度交付。现有 GitHub PR 未显示自动检查结果。
