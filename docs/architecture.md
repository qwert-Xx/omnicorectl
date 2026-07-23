# Architecture / 架构

Status: accepted, 2026-07-22

状态：已接受，2026-07-22

## Goals / 目标

`omnicorectl` is a Linux-friendly CLI for inspecting and administering ABB
OmniCore controllers through RWS 2.0. Its first target is RobotWare 8.1, while
the protocol code tolerates additive fields and minor RobotWare differences.

`omnicorectl` 是一个适合 Linux 环境、通过 RWS 2.0 检查和管理 ABB OmniCore
控制器的 CLI。首个目标版本是 RobotWare 8.1，同时协议代码应容忍新增字段和小幅
RobotWare 差异。

Important constraints include controller sessions, explicit media types,
factory self-signed certificates, the documented request-rate limit, and the
RobotWare 8 Control Station/write-access workflow. Commands must not leak
credentials or leave write access held after exit.

重要约束包括控制器会话、显式媒体类型、出厂自签名证书、文档规定的请求速率上限，
以及 RobotWare 8 控制站/写权限工作流。命令不得泄露凭据，也不得在退出后继续占用
写权限。

## Language convention / 语言约定

Maintainer-facing documentation, docstrings, meaningful code comments, and
explicit CLI help use English first with a corresponding Chinese explanation.
Protocol field names, code identifiers, machine-readable JSON keys, controller
payloads, and test fixtures remain unchanged so wire behavior stays stable.

面向维护者的文档、docstring、有实际意义的代码注释和显式 CLI 帮助采用英文在前、
中文对应说明的形式。协议字段名、代码标识符、机器可读 JSON 键、控制器报文和测试
夹具保持不变，以保证传输行为稳定。

## Projects reviewed / 已调研项目

### ABB RWS OpenAPI

Sources / 来源：

- <https://robotwebservices.robotics.abb.com/>
- <https://developercenter.robotstudio.com/api/RWS>

ABB publishes service-specific OpenAPI 3 definitions. They are authoritative
for paths, verbs, form fields, media types, and examples. They are not a runtime
dependency and are not blindly generated into this client: the examined RAPID,
I/O, and CFG definitions lack `operationId` values and reusable response
schemas, while RWS returns dynamic HAL+JSON or XHTML resources. Online docs can
also lag controller behavior, so live read-only probes and controller responses
serve as additional compatibility evidence.

ABB 按服务发布 OpenAPI 3 定义，是路径、方法、表单字段、媒体类型和示例的权威依据。
本项目不把它们作为运行时依赖，也不盲目生成客户端：所检查的 RAPID、I/O 和 CFG
定义缺少 `operationId` 与可复用响应模式，而 RWS 返回动态 HAL+JSON 或 XHTML
资源。在线文档也可能落后于控制器行为，因此只读实机探测和控制器响应也是兼容性
证据。

Decision: keep endpoint mapping explicit and traceable to OpenAPI. A future
development-time checker may compare endpoint declarations with ABB specs.

决定：保持端点映射显式且可追溯到 OpenAPI；未来可增加开发期检查器，把端点声明与
ABB 规范进行对比。

### `abb_robot_client` (Python)

Source / 来源：<https://github.com/rpiRobotics/abb_robot_client>

This project validates the usefulness of one session boundary and typed domain
results. Its RWS implementation targets RobotWare 6 and explicitly excludes
RobotWare 7+, and its synchronous/asynchronous implementations duplicate much
endpoint logic.

该项目证明了集中会话边界和类型化领域结果的价值。但其 RWS 实现面向 RobotWare 6，
明确不支持 RobotWare 7+，同步与异步实现还重复了大量端点逻辑。

Decision: use a central session and typed results, target RWS 2.0 only, and
start synchronously. Add an asynchronous surface only for a demonstrated need.

决定：采用集中会话和类型化结果，仅面向 RWS 2.0，并从同步 API 开始；只有实际需求
成立后才增加异步接口。

### `abb_librws` (C++)

Source / 来源：<https://github.com/ros-industrial/abb_librws>

Its separation of HTTP, general RWS operations, RAPID helpers, configuration,
and higher-level workflows is valuable. Its C++/Poco/ROS stack and older-RWS
focus are unnecessarily heavy for this portable administration CLI.

它把 HTTP、通用 RWS 操作、RAPID 辅助、配置和高层工作流分离，这一设计很有价值；
但 C++/Poco/ROS 技术栈及旧版 RWS 定位对本项目的便携管理 CLI 来说过重。

Decision: retain the protocol/workflow separation without adopting its runtime
stack or state-machine specialization.

决定：保留协议原语与运维工作流的分层，不采用其运行时栈和状态机专用设计。

### `abb-rws-client` and ABB Robot VS Code extension (TypeScript)

Sources / 来源：

- <https://github.com/ichbinmeraj/abb-rws-vscode>
- <https://www.npmjs.com/package/abb-rws-client>

This reference separates HTTP sessions, parsers, resource mapping, version
adapters, subscriptions, and the higher-level robot manager. It also covers
throttling, cookies, cleanup, polling fallback, and typed errors, while keeping
UI concerns outside the protocol layer.

该参考实现分离了 HTTP 会话、解析器、资源映射、版本适配、订阅和高层机器人管理器，
并处理节流、Cookie、会话清理、轮询回退及类型化错误，同时把 UI 关注点留在协议层
之外。

Decision: adopt the broad separation of concerns, but omit version adapters and
a permanently polling manager because this short-lived CLI deliberately targets
OmniCore/RWS 2.0 only. Every invocation owns and deterministically closes one
bounded session.

决定：采用这种总体关注点分离，但不引入版本适配器和常驻轮询管理器，因为该短生命周期
CLI 明确只支持 OmniCore/RWS 2.0。每次调用独占一个有界会话并确定性关闭。

## Chosen stack / 技术选型

- Python 3.10 or newer. / Python 3.10 或更高版本。
- `httpx` for Basic authentication, cookies, explicit timeouts, streaming, and
  injectable mock transports. / 使用 `httpx` 处理 Basic 认证、Cookie、显式超时、
  流式传输和可注入模拟传输。
- Standard-library `argparse` for a dependency-light command tree.
  / 使用标准库 `argparse` 构建轻依赖命令树。
- `dataclasses` and tolerant mapping parsers rather than strict validation, so
  additive ABB fields do not break clients. / 使用 `dataclasses` 和宽容型映射解析器，
  避免 ABB 新增字段破坏客户端。
- `unittest` and `httpx.MockTransport` for deterministic protocol tests; live
  controller checks remain explicit integration tests. / 使用 `unittest` 和
  `httpx.MockTransport` 做确定性协议测试，实机检查保持为显式集成测试。

## Layers / 分层

```text
CLI commands / CLI 命令
    -> application services / 应用服务 (controller, rapid, io, cfg, files, backup)
        -> RWS endpoint client and parsers / RWS 端点客户端与解析器
            -> HTTP transport/session / HTTP 传输与会话
                -> OmniCore controller / OmniCore 控制器
```

Current package layout / 当前包结构：

```text
src/omnicorectl/
  cli.py                 argument parsing, exit codes, output selection / 参数、退出码、输出
  errors.py              user-facing exception hierarchy / 面向用户的异常层次
  output.py              table, JSON, and raw output / 表格、JSON 与原始输出
  rws/
    hal.py               tolerant HAL+JSON parsing / 宽容型 HAL+JSON 解析
    client.py            HTTPS session, throttling, streaming, errors / 会话、节流、流与错误
  services/
    controller.py        status and lifecycle / 状态与生命周期
    rapid.py             tasks, modules, and source / 任务、模块与源码
    io.py                networks, devices, signals / 网络、设备与信号
    cfg.py               guarded configuration mutation / 受保护的配置修改
    control_station.py   RW8 write-access lifecycle / RW8 写权限生命周期
    files.py             file operations and path guards / 文件操作与路径保护
    backup.py            asynchronous backup lifecycle / 异步备份生命周期
```

Configuration resolution remains in `cli.py`; HTTPS transport and error parsing
share one boundary in `rws/client.py`. Split them only when an independent
consumer appears, avoiding empty modules and pass-through abstractions.

配置解析继续放在 `cli.py`；HTTPS 传输和错误解析共享 `rws/client.py` 中的会话边界。
只有出现独立消费者时才拆分，避免空模块和纯转发抽象。

## Command contract / 命令契约

- Nouns form groups: `controller`, `rapid`, `io`, `cfg`, `file`, `backup`, and
  `controlstation`. / 名词构成命令组。
- Verbs describe one operation: `status`, `list`, `get`, `set`, `create`, and
  `delete`. / 动词描述单一操作。
- Read commands default to concise text and support `--json`.
  / 读取命令默认输出简洁文本，并支持 `--json`。
- Source and file bytes go to stdout or an explicit file; diagnostics go to
  stderr. / 源码和文件字节写入标准输出或明确文件，诊断信息写入标准错误。
- Exit `0` means success; `2` means CLI/configuration error; other stable codes
  distinguish auth, authorization, network, and RWS failures.
  / 退出码 `0` 表示成功，`2` 表示 CLI/配置错误，其他稳定退出码区分认证、授权、
  网络和 RWS 错误。
- Reads never mutate implicitly. / 读取命令绝不隐式修改状态。
- Write access is released in `finally`, including after errors and interrupts.
  / 写权限在 `finally` 中释放，包括错误或中断场景。

The verified Control Station lifecycle is documented in
[`control-station.md`](control-station.md).

已验证的控制站生命周期见 [`control-station.md`](control-station.md)。

```bash
OMNICORE_PASSWORD=... omnicorectl \
  --host 192.168.125.1 --username codex --insecure \
  controller status --json
```

`--password` is intentionally absent because process arguments and shell history
can expose it. Without the environment variable, an interactive prompt is used.

项目有意不提供 `--password`，因为进程参数和 Shell 历史可能泄露密码；未设置环境变量
时使用交互式提示。

## Testing strategy / 测试策略

Each feature commit includes, as applicable:

每个功能提交按适用情况包括：

1. parser/service unit tests with sanitized response shapes;
   使用脱敏响应结构的解析器/服务单元测试；
2. CLI output and exit tests;
   CLI 输出和退出行为测试；
3. a read-only live check against the connected RW8.1 controller;
   对已连接 RW8.1 控制器的只读实机检查；
4. for writes, pre-read, scoped mutation, readback, and guaranteed access release;
   写操作执行预读、有界修改、回读并保证释放权限；
5. no credentials, cookies, backups, or generated local profiles in Git.
   Git 中不得包含凭据、Cookie、备份或生成的本地配置。

Live tests require physical hardware and are excluded from the default unit
suite. Sanitized results are recorded in
[`live-validation.md`](live-validation.md).

实机测试需要物理硬件，因此不进入默认单元测试套件；脱敏结果记录在
[`live-validation.md`](live-validation.md)。

## Deferred decisions / 延后决策

- WebSocket subscriptions wait for a `watch` use case.
  / WebSocket 订阅延后到实现 `watch` 场景。
- Multi-controller orchestration and named profiles are deferred.
  / 多控制器编排和命名配置文件暂缓。
- RWS 1.0/IRC5 is out of scope; any future support belongs in a protocol adapter,
  not scattered conditionals. / RWS 1.0/IRC5 不在范围内；未来若支持，应使用协议适配器，
  而不是散落的条件分支。
- OpenAPI generation remains development tooling until generated code is clearer
  and better tested than explicit mappings. / OpenAPI 生成仍只作为开发工具，直到生成代码
  比显式映射更清晰且测试更充分。
