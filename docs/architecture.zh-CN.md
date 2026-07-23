# 架构

[English](architecture.md) | 简体中文

状态：已接受，2026-07-22

## 目标

`omnicorectl` 是一个适合 Linux 环境、通过 RWS 2.0 检查和管理 ABB OmniCore
控制器的 CLI。首个目标版本是 RobotWare 8.1，同时协议代码应容忍新增字段和小幅
RobotWare 差异。

重要约束包括控制器会话、显式媒体类型、出厂自签名证书、文档规定的请求速率上限，
以及 RobotWare 8 控制站/写权限工作流。命令不得泄露凭据，也不得在退出后继续占用
写权限。

## 语言约定

英文和简体中文说明文档存放在独立文件中。英文文件使用 `.md` 后缀，对应的中文文件
使用 `.zh-CN.md`。面向维护者的 docstring、有实际意义的代码注释和显式 CLI 帮助
仍同时包含两种语言，因为它们紧邻可执行代码，不属于独立说明文档。

协议字段名、代码标识符、机器可读 JSON 键、控制器报文和测试夹具保持不变，以保证
传输行为稳定。

## 已调研项目

### ABB RWS OpenAPI

来源：

- <https://robotwebservices.robotics.abb.com/>
- <https://developercenter.robotstudio.com/api/RWS>

ABB 按服务发布 OpenAPI 3 定义，是路径、方法、表单字段、媒体类型和示例的权威依据。
本项目不把它们作为运行时依赖，也不盲目生成客户端：所检查的 RAPID、I/O 和 CFG
定义缺少 `operationId` 与可复用响应模式，而 RWS 返回动态 HAL+JSON 或 XHTML
资源。在线文档也可能落后于控制器行为，因此只读实机探测和控制器响应也是兼容性
证据。

决定：保持端点映射显式且可追溯到 OpenAPI；未来可增加开发期检查器，把端点声明与
ABB 规范进行对比。

### `abb_robot_client`（Python）

来源：<https://github.com/rpiRobotics/abb_robot_client>

该项目证明了集中会话边界和类型化领域结果的价值。但其 RWS 实现面向 RobotWare 6，
明确不支持 RobotWare 7+，同步与异步实现还重复了大量端点逻辑。

决定：采用集中会话和类型化结果，仅面向 RWS 2.0，并从同步 API 开始；只有实际需求
成立后才增加异步接口。

### `abb_librws`（C++）

来源：<https://github.com/ros-industrial/abb_librws>

它把 HTTP、通用 RWS 操作、RAPID 辅助、配置和高层工作流分离，这一设计很有价值；
但 C++/Poco/ROS 技术栈及旧版 RWS 定位对本项目的便携管理 CLI 来说过重。

决定：保留协议原语与运维工作流的分层，不采用其运行时栈和状态机专用设计。

### `abb-rws-client` 与 ABB Robot VS Code 扩展（TypeScript）

来源：

- <https://github.com/ichbinmeraj/abb-rws-vscode>
- <https://www.npmjs.com/package/abb-rws-client>

该参考实现分离了 HTTP 会话、解析器、资源映射、版本适配、订阅和高层机器人管理器，
并处理节流、Cookie、会话清理、轮询回退及类型化错误，同时把 UI 关注点留在协议层
之外。

决定：采用这种总体关注点分离，但不引入版本适配器和常驻轮询管理器，因为该短生命周期
CLI 明确只支持 OmniCore/RWS 2.0。每次调用独占一个有界会话并确定性关闭。

## 技术选型

- Python 3.10 或更高版本。
- 使用 `httpx` 处理 Basic 认证、Cookie、显式超时、流式传输和可注入模拟传输。
- 使用标准库 `argparse` 构建轻依赖命令树。
- 使用 `dataclasses` 和宽容型映射解析器，避免 ABB 新增字段破坏客户端。
- 使用 `unittest` 和 `httpx.MockTransport` 做确定性协议测试，实机检查保持为显式
  集成测试。

## 分层

```text
CLI 命令
    -> 应用服务（controller、rapid、io、cfg、files、backup）
        -> RWS 端点客户端与解析器
            -> HTTP 传输与会话
                -> OmniCore 控制器
```

当前包结构：

```text
src/omnicorectl/
  cli.py                 参数解析、退出码、输出选择
  rapid_cli.py           RAPID 命令树与受保护 CLI 工作流
  errors.py              面向用户的异常层次
  output.py              表格、JSON 与原始输出
  rws/
    hal.py               宽容型 HAL+JSON 解析
    client.py            HTTPS 会话、节流、流式传输和错误
  services/
    controller.py        状态与生命周期
    rapid.py             源码、模块、程序与任务原语
    rapid_debug.py       执行、程序指针、断点与符号
    rapid_editing.py     受检查的编辑、部署、构建与回滚
    io.py                网络、设备与信号
    cfg.py               受保护的配置修改
    control_station.py   RW8 写权限生命周期
    files.py             文件操作与路径保护
    backup.py            异步备份生命周期
```

配置解析继续放在 `cli.py`；HTTPS 传输和错误解析共享 `rws/client.py` 中的会话边界。
只有出现独立消费者时才拆分，避免空模块和纯转发抽象。

## 命令契约

- 名词构成命令组：`controller`、`rapid`、`io`、`cfg`、`file`、`backup` 和
  `controlstation`。
- 动词描述单一操作：`status`、`list`、`get`、`set`、`create` 和 `delete`。
- 读取命令默认输出简洁文本，并支持 `--json`。
- 源码和文件字节写入标准输出或明确文件，诊断信息写入标准错误。
- 退出码 `0` 表示成功，`2` 表示 CLI/配置错误，其他稳定退出码区分认证、授权、网络
  和 RWS 错误。
- 读取命令绝不隐式修改状态。
- 写权限在 `finally` 中释放，包括错误或中断场景。

已验证的控制站生命周期见 [`control-station.zh-CN.md`](control-station.zh-CN.md)。
RAPID 编辑事务和命令界面见 [`rapid.zh-CN.md`](rapid.zh-CN.md)。

```bash
OMNICORE_PASSWORD=... omnicorectl \
  --host 192.168.125.1 --username codex --insecure \
  controller status --json
```

项目有意不提供 `--password`，因为进程参数和 Shell 历史可能泄露密码；未设置环境变量
时使用交互式提示。

## 测试策略

每个功能提交按适用情况包括：

1. 使用脱敏响应结构的解析器/服务单元测试；
2. CLI 输出和退出行为测试；
3. 对已连接 RW8.1 控制器的只读实机检查；
4. 写操作执行预读、有界修改、回读并保证释放权限；
5. Git 中不得包含凭据、Cookie、备份或生成的本地配置。

实机测试需要物理硬件，因此不进入默认单元测试套件；脱敏结果记录在
[`live-validation.zh-CN.md`](live-validation.zh-CN.md)。

## 延后决策

- WebSocket 订阅延后到实现 `watch` 场景。
- 多控制器编排和命名配置文件暂缓。
- RWS 1.0/IRC5 不在范围内；未来若支持，应使用协议适配器，而不是散落的条件分支。
- OpenAPI 生成仍只作为开发工具，直到生成代码比显式映射更清晰且测试更充分。
