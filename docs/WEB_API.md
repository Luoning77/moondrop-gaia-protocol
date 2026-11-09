# 本地 Web 调试接口

[返回项目首页](../README.md)

服务默认监听 `127.0.0.1:8080`。以下接口供本地调试面板使用。

| 路径 | 说明 |
|------|------|
| `GET /api/status` | 查看串口连接和设备在线状态 |
| `GET /api/check` | 发送探测命令，检查设备是否响应 |
| `GET /api/state` | 一次读取固件/电量/ANC/手势/增益/LED/提示音/LHDC/一拖二 |
| `GET /api/set/anc?mode=0..4` | 设置降噪，写后重读 |
| `GET /api/set/gain?level=0..2` | 设置增益，写后重读 |
| `GET /api/set/led?on=0/1` | 设置指示灯，写后重读 |
| `GET /api/set/touch?hex=<10位十六进制>` | 整包写 5 字节手势，写后重读 |
| `GET /api/set/tone?enabled=&volume=&index=` | 写提示音 3 字节（`index` = 提示音组号 0–255），写后重读 |
| `GET /api/set/lhdc?on=0/1` | LHDC 开关，写后重读 |
| `GET /api/set/multipoint?on=0/1` | 一拖二开关，写后重读 |
| `GET /api/send?feature=&cmd=&payload=` | 自定义命令 |
| `GET /api/presets` | 快捷读取预设 |

> 写接口（`/api/set/*`、`/api/send`）会拒绝浏览器发起的跨源请求（返回 403）；curl 等不带 `Origin`/`Referer` 的本地调用不受影响。
>
> `/api/send` 的 `feature`/`cmd` 按 Python 整数字面量解析：`40` 表示十进制 40（`0x28`），`0x40` 才是 ANC 的 `0x40`；页面会自动把输入的十六进制转成十进制。
> 只有已知的幂等查询会自动重试一次。

`/api/state` 返回 `aborted_early: true` 时，`state` 仅包含中断前成功读到的字段。`connected` 表示串口是否打开，`online` 表示本次请求是否收到匹配应答且未遇到明确的串口故障。
