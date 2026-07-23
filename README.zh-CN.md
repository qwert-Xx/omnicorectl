# omnicorectl

[English](README.md) | 简体中文

`omnicorectl` 是一个通过 Robot Web Services（RWS）2.0 管理 ABB OmniCore
控制器的命令行客户端。项目有意保持对 RobotStudio 和 ABB PC SDK 的独立性，
并以运行 RobotWare 8.1 的 OmniCore 控制器作为开发目标。

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## 控制器操作

```bash
export OMNICORE_HOST=192.168.125.1
export OMNICORE_USERNAME=codex
export OMNICORE_PASSWORD='set-this-outside-shell-history'
# 仅写命令需要；这是由客户端自行选择的数字 PIN。
export OMNICORE_CONTROL_STATION_PIN='set-a-numeric-pin'

# 出厂证书通常是自签名证书。
.venv/bin/omnicorectl --insecure controller status
.venv/bin/omnicorectl --insecure controller status --json

# 列出 RAPID 任务，不改变执行状态。
.venv/bin/omnicorectl --insecure rapid tasks
.venv/bin/omnicorectl --insecure rapid tasks --json

# 列出任务中的程序模块和系统模块。
.venv/bin/omnicorectl --insecure rapid modules T_ROB1

# 读取模块源码，不修改控制器。
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion > EGM_StreamMotion.mod

# 浏览 I/O 网络、设备和信号。
.venv/bin/omnicorectl --insecure io networks
.venv/bin/omnicorectl --insecure io devices EtherCAT
.venv/bin/omnicorectl --insecure io signals
.venv/bin/omnicorectl --insecure io signals --network EtherCAT --device EC_Internal_Device
.venv/bin/omnicorectl --insecure io signals --type DI --json

# 读取信号状态与访问元数据。
.venv/bin/omnicorectl --insecure io get SC_Feedback_Net SC_Feedback_Dev SafetyEnable

# 浏览控制器配置数据库。
.venv/bin/omnicorectl --insecure cfg domains
.venv/bin/omnicorectl --insecure cfg types EIO
.venv/bin/omnicorectl --insecure cfg instances EIO ETHERCAT_INTERNAL_DEVICE
.venv/bin/omnicorectl --insecure cfg instances EIO EIO_SIGNAL --json
.venv/bin/omnicorectl --insecure cfg get EIO ETHERCAT_INTERNAL_DEVICE EC_Internal_Device

# 更新、校验并回读一个属性。
.venv/bin/omnicorectl --insecure cfg set EIO EIO_SIGNAL MySignal Label 'new label' --yes

# 创建、初始化、校验并验证外部实例；失败时自动删除新实例。
.venv/bin/omnicorectl --insecure cfg create EIO EIO_SIGNAL EtherCAT_DI \
  --set SignalType=DI \
  --set Device=EC_Internal_Device \
  --set DeviceMap=0 \
  --yes

# 校验、删除并确认实例已不存在。
.venv/bin/omnicorectl --insecure cfg delete EIO EIO_SIGNAL EtherCAT_DI --yes

# 浏览控制器文件卷和目录。
.venv/bin/omnicorectl --insecure file list
.venv/bin/omnicorectl --insecure file list '$HOME'

# 原子下载；--force 允许覆盖。
.venv/bin/omnicorectl --insecure file download '$HOME/sc_vsm_metadata.xml' ./sc_vsm_metadata.xml

# 上传文件，默认不覆盖已有文件。
.venv/bin/omnicorectl --insecure file upload ./local.bin '$TEMP/local.bin'

# 永久删除需要明确确认。
.venv/bin/omnicorectl --insecure file delete '$TEMP/local.bin' --yes

# 读取备份状态或创建 tar 备份。
.venv/bin/omnicorectl --insecure backup status
.venv/bin/omnicorectl --insecure backup create '$TEMP/backup_20260722'

# 检查外部控制与写权限状态。
.venv/bin/omnicorectl --insecure controlstation status

# 仅请求普通暖启动。
.venv/bin/omnicorectl --insecure controller restart --yes
```

全局连接选项必须写在命令组之前。`--host` 和 `--username` 会覆盖对应的环境变量。

架构与增量开发规则见 [`docs/architecture.zh-CN.md`](docs/architecture.zh-CN.md)。

## 安全规则

- 密码来自交互式提示或 `OMNICORE_PASSWORD`，绝不写入项目配置。
- 默认启用 TLS 校验；出厂自签名证书需要显式使用 `--insecure`。
- 控制器流量忽略代理环境变量。
- 修改命令只在有界的控制站生命周期内持有写权限。破坏性操作需要确认，文件与
  CFG 写入按需执行保护、校验、回读或回滚。

## 开发验证

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q src tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy src
.venv/bin/python -m pip wheel --no-deps . --wheel-dir /tmp/omnicorectl-wheel
```

经过脱敏的 RW 8.1 集成验证结果记录在
[`docs/live-validation.zh-CN.md`](docs/live-validation.zh-CN.md)。
