# MOONDROP Pudding Protocol

水月雨布丁（MOONDROP Pudding，MD-TWS-056）的蓝牙控制协议库和本地 Web 调试面板。

🌐 [English](README_EN.md) | 简体中文

## 📖 简介

项目根据蓝牙 HCI 抓包和 MOONDROP Link APK 分析整理，覆盖布丁通过蓝牙 SPP（RFCOMM）收发的 GAIA V3 命令。现有逆向记录基于固件 `3.5.2` 和 MOONDROP Link `2.23.1c`。其他型号或固件的兼容性需单独验证。

## ✨ 功能

| 组件 | 用途 |
| --- | --- |
| Kotlin/JVM 协议库 | 构造命令、编码和解析数据帧。流式解码器可处理分包和粘包，蓝牙连接由调用方负责。 |
| 本地 Web 面板 | 读取三端电量，调节降噪、增益、指示灯、提示音、左右耳手势、LHDC 和一拖二，查看 LC3 / LDAC 状态。 |
| 串口调试 | 发送自定义命令并查看 TX / RX 十六进制日志。面板会在写入设置后重读，部分命令即使没有 ACK 也可通过读回确认。 |
| 演示模式 | 使用内置模拟设备，可模拟写入无 ACK 和设备响应延迟。 |

## 🚀 快速开始

准备 Python 3.8 或更新版本。在仓库根目录安装依赖并启动演示：

```bash
python -m pip install -r requirements.txt
python tools/webtest.py --demo
```

浏览器打开 [本地面板](http://127.0.0.1:8080)。如果系统的 Python 3 命令是 `python3`，将下文的 `python` 一并替换。Windows 也可运行 `run-demo.bat`。

![演示模式下的 Web 调试面板](docs/webtest-demo.png)

### 在 Windows 连接耳机

1. 在系统蓝牙设置中配对布丁，确认系统已为它分配出站蓝牙 COM 端口。
2. 退出手机上的 MOONDROP Link，避免控制连接被占用。
3. 运行下面第一条命令自动查找串口。如果没找到，改用第二条命令，将 `COM8` 换成实际端口。

```powershell
.\run-pudding.bat
.\run-pudding.bat COM8
```

| 参数 | 用途 |
| --- | --- |
| `--port COM8` | 直接运行 `tools/webtest.py` 时指定串口 |
| `--find-port` | 仅输出自动找到的串口，未找到时输出 `NONE` |
| `--web-port 9090` | 将本地 Web 端口改为 9090 |
| `--demo --demo-noack` | 模拟写入后无 ACK |
| `--demo --demo-latency 0.3` | 模拟 0.3 秒设备延迟 |

## 📦 Kotlin 库

使用 JDK 17，在仓库根目录运行 Gradle Wrapper。Windows 将 `./gradlew` 换成 `.\gradlew.bat`。

```bash
./gradlew build
```

JAR 输出到 `build/libs/`。Gradle 从 [version.properties](version.properties) 读取项目版本并用于 JAR 文件名，版本号按「年.大版本.构建次数」手动维护。

```kotlin
import com.moondrop.protocol.GaiaPacketBuilder
import com.moondrop.protocol.ResponseParser
import com.moondrop.protocol.codec.GaiaCodec

val ancQuery = GaiaCodec.encode(GaiaPacketBuilder.ancQuery())
val decoder = GaiaCodec.StreamDecoder()

fun onBytesReceived(bytes: ByteArray) {
    for (packet in decoder.feed(bytes)) {
        ResponseParser.parseAncMode(packet)?.let { println(it) }
    }
}
```

将 `ancQuery` 写入已打开的 SPP 连接，再将读到的字节分批传给 `onBytesReceived`。每条连接各自保留一个解码器。

## 🧪 测试

```bash
./gradlew test
python -m pip install -r requirements.txt pytest
python -m pytest tools/test_webtest.py
```

## 📚 文档与参考资料

- [协议参考](docs/PROTOCOL.md)记录帧格式、命令编号和参数。
- [本地 Web API](docs/WEB_API.md)记录面板使用的接口。
- [早期逆向记录](docs/MOONDROP_Pudding_逆向结果.md)保留抓包分析和 EQ 研究。
- 相关项目包括 [SpaceTravel-Protocol](https://github.com/pubglite55/SpaceTravel-Protocol) 和 [moondrop-spp-controller](https://github.com/ribentianhuang38-boop/moondrop-spp-controller)。

## 📄 许可证

[MIT](LICENSE)
