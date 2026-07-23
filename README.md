# omnicorectl

`omnicorectl` is a command-line client for ABB OmniCore controllers using Robot
Web Services (RWS) 2.0. It is intentionally independent of RobotStudio and ABB
PC SDK, and is developed against an OmniCore controller running RobotWare 8.1.

`omnicorectl` 是一个通过 Robot Web Services（RWS）2.0 管理 ABB OmniCore
控制器的命令行客户端。项目有意保持对 RobotStudio 和 ABB PC SDK 的独立性，
并以运行 RobotWare 8.1 的 OmniCore 控制器作为开发目标。

## Installation / 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Controller operations / 控制器操作

```bash
export OMNICORE_HOST=192.168.125.1
export OMNICORE_USERNAME=codex
export OMNICORE_PASSWORD='set-this-outside-shell-history'
# Required only by write commands; this is a client-selected numeric PIN.
# 仅写命令需要；这是由客户端自行选择的数字 PIN。
export OMNICORE_CONTROL_STATION_PIN='set-a-numeric-pin'

# Factory certificates are normally self-signed. / 出厂证书通常是自签名证书。
.venv/bin/omnicorectl --insecure controller status
.venv/bin/omnicorectl --insecure controller status --json

# List RAPID tasks without changing execution state. / 列出 RAPID 任务，不改变执行状态。
.venv/bin/omnicorectl --insecure rapid tasks
.venv/bin/omnicorectl --insecure rapid tasks --json

# List modules in a task. / 列出任务中的程序模块和系统模块。
.venv/bin/omnicorectl --insecure rapid modules T_ROB1

# Read module source without modifying it. / 读取模块源码，不修改控制器。
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion > EGM_StreamMotion.mod

# Browse I/O networks, devices, and signals. / 浏览 I/O 网络、设备和信号。
.venv/bin/omnicorectl --insecure io networks
.venv/bin/omnicorectl --insecure io devices EtherCAT
.venv/bin/omnicorectl --insecure io signals
.venv/bin/omnicorectl --insecure io signals --network EtherCAT --device EC_Internal_Device
.venv/bin/omnicorectl --insecure io signals --type DI --json

# Read signal state and access metadata. / 读取信号状态与访问元数据。
.venv/bin/omnicorectl --insecure io get SC_Feedback_Net SC_Feedback_Dev SafetyEnable

# Browse controller configuration. / 浏览控制器配置数据库。
.venv/bin/omnicorectl --insecure cfg domains
.venv/bin/omnicorectl --insecure cfg types EIO
.venv/bin/omnicorectl --insecure cfg instances EIO ETHERCAT_INTERNAL_DEVICE
.venv/bin/omnicorectl --insecure cfg instances EIO EIO_SIGNAL --json
.venv/bin/omnicorectl --insecure cfg get EIO ETHERCAT_INTERNAL_DEVICE EC_Internal_Device

# Update, validate, and re-read one attribute. / 更新、校验并回读一个属性。
.venv/bin/omnicorectl --insecure cfg set EIO EIO_SIGNAL MySignal Label 'new label' --yes

# Create, initialize, validate, and verify an external instance.
# 创建、初始化、校验并验证一个外部实例；失败时自动删除新实例。
.venv/bin/omnicorectl --insecure cfg create EIO EIO_SIGNAL EtherCAT_DI \
  --set SignalType=DI \
  --set Device=EC_Internal_Device \
  --set DeviceMap=0 \
  --yes

# Validate, delete, and verify absence. / 校验、删除并确认实例已不存在。
.venv/bin/omnicorectl --insecure cfg delete EIO EIO_SIGNAL EtherCAT_DI --yes

# Browse controller files. / 浏览控制器文件卷和目录。
.venv/bin/omnicorectl --insecure file list
.venv/bin/omnicorectl --insecure file list '$HOME'

# Download atomically; --force permits replacement. / 原子下载；--force 允许覆盖。
.venv/bin/omnicorectl --insecure file download '$HOME/sc_vsm_metadata.xml' ./sc_vsm_metadata.xml

# Upload without overwriting by default. / 上传文件，默认不覆盖已有文件。
.venv/bin/omnicorectl --insecure file upload ./local.bin '$TEMP/local.bin'

# Permanent deletion requires confirmation. / 永久删除需要明确确认。
.venv/bin/omnicorectl --insecure file delete '$TEMP/local.bin' --yes

# Read backup state or create a tar backup. / 读取备份状态或创建 tar 备份。
.venv/bin/omnicorectl --insecure backup status
.venv/bin/omnicorectl --insecure backup create '$TEMP/backup_20260722'

# Inspect external-control/write-access state. / 检查外部控制与写权限状态。
.venv/bin/omnicorectl --insecure controlstation status

# Request only a normal warm restart. / 仅请求普通暖启动。
.venv/bin/omnicorectl --insecure controller restart --yes
```

Global connection options must precede the command group. `--host` and
`--username` override their corresponding environment variables.

全局连接选项必须写在命令组之前。`--host` 和 `--username` 会覆盖对应的环境变量。

Architecture and incremental development rules are documented in
[`docs/architecture.md`](docs/architecture.md).

架构与增量开发规则见 [`docs/architecture.md`](docs/architecture.md)。

## Security rules / 安全规则

- Passwords come from an interactive prompt or `OMNICORE_PASSWORD`; project
  configuration never stores them.
  密码来自交互式提示或 `OMNICORE_PASSWORD`，绝不写入项目配置。
- TLS verification is enabled by default. Factory self-signed certificates
  require an explicit `--insecure` option.
  默认启用 TLS 校验；出厂自签名证书需要显式使用 `--insecure`。
- Controller traffic ignores proxy environment variables.
  控制器流量忽略代理环境变量。
- Mutating commands use a bounded Control Station write-access lifecycle.
  Destructive operations require confirmation; file and CFG writes include
  guards, validation, readback, or rollback as applicable.
  修改命令只在有界的控制站生命周期内持有写权限。破坏性操作需要确认，文件与
  CFG 写入按需执行保护、校验、回读或回滚。

## Development verification / 开发验证

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q src tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy src
.venv/bin/python -m pip wheel --no-deps . --wheel-dir /tmp/omnicorectl-wheel
```

Sanitized RW 8.1 integration results are recorded in
[`docs/live-validation.md`](docs/live-validation.md).

经过脱敏的 RW 8.1 集成验证结果记录在
[`docs/live-validation.md`](docs/live-validation.md)。
