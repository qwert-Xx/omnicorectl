# Live-controller validation / 实机控制器验证

This file records sanitized integration evidence excluded from the deterministic
unit suite. It contains no passwords, PINs, cookies, or backup contents.

本文记录不进入确定性单元测试套件的脱敏集成证据，不包含密码、PIN、Cookie 或备份
内容。

## Target / 目标

- Validation dates / 验证日期：2026-07-22 and / 及 2026-07-23
- Controller / 控制器：real / 真实 OmniCore V250XT
- RobotWare：`8.1.0+600`
- RWS endpoint / RWS 端点：controller HTTPS service port / 控制器 HTTPS 服务端口
- Representation / 表示形式：`application/hal+json;v=2.0`

## Read-only coverage / 只读覆盖

The installed CLI successfully read the following resources:

已安装的 CLI 成功读取以下资源：

- controller identity, operation mode, controller state, and RAPID state;
  控制器身份、操作模式、控制器状态和 RAPID 状态；
- RAPID tasks, module inventory, and module source;
  RAPID 任务、模块清单和模块源码；
- I/O networks, devices, signal inventory, and detailed signal state;
  I/O 网络、设备、信号清单和详细信号状态；
- CFG domains, types, instances, and attributes;
  CFG 域、类型、实例和属性；
- file directories and files, backup state, and Control Station status.
  文件目录与文件、备份状态和控制站状态。

The completion preflight observed RAPID stopped, backup state `Backup Ready`,
external control enabled, and no station holding write access. The controller
was in emergency stop during the audit.

完成前检查观察到 RAPID 已停止、备份状态为 `Backup Ready`、外部控制已启用，且没有
控制站持有写权限；审计期间控制器处于急停状态。

## Reversible file write / 可逆文件写入

A unique `$TEMP` probe exercised this workflow:

一个唯一的 `$TEMP` 探针验证了以下流程：

1. register a remote Control Station / 注册远程控制站；
2. acquire and verify scoped write access / 获取并验证有界写权限；
3. upload `README.md` as binary data / 将 `README.md` 作为二进制数据上传；
4. release access / 释放权限；
5. download through another CLI invocation / 通过另一次 CLI 调用下载；
6. compare SHA-256 byte-for-byte / 逐字节比较 SHA-256；
7. reacquire access, delete, and confirm absence / 重新获取权限、删除并确认不存在；
8. verify final status `held=false`, holder `none` / 验证最终状态无人持有写权限。

The completion audit repeated the workflow after adding the ordinary-file delete
guard. A 4,806-byte probe passed upload, download, hash comparison, parent-path
preflight, type verification, deletion, and absence verification. Its SHA-256 was
`94d05228aff4f9d3de5725b91c8b94b229cc3e5b34fc5822ff15213085c101eb`.

增加普通文件删除保护后，完成审计再次执行了该流程。4,806 字节探针通过上传、下载、
哈希比较、父路径预检、类型验证、删除和不存在性验证，其 SHA-256 为
`94d05228aff4f9d3de5725b91c8b94b229cc3e5b34fc5822ff15213085c101eb`。

## CFG and EtherCAT I/O / CFG 与 EtherCAT I/O

The CFG create workflow created and validated two external signals plus Cross
Data and Transfer Data instances. A normal warm restart activated them:

CFG 创建工作流创建并校验了两个外部信号，以及 Cross Data 和 Transfer Data 实例；
普通暖启动使其生效：

| Type / 类型 | Instance / 实例 | Mapping / 映射 |
|---|---|---|
| `EIO_SIGNAL` | `EtherCAT_DI` | DI, `EC_Internal_Device`, bit 0 / 输入位 0 |
| `EIO_SIGNAL` | `EtherCAT_DO` | DO, `EC_Internal_Device`, bit 0 / 输出位 0 |
| `EIO_CROSS` | `EtherCAT_CrossLoopback` | `EtherCAT_DI` → `EtherCAT_DO` |
| `EIO_DEVICE_TRANSFER_DATA` | `EtherCAT_RawLoopback` | input bits 8–15 → output bits 8–15 / 输入位 8–15 → 输出位 8–15 |

An official SOEM v2.0.0 master connected through `ens6f3` to `ECAT IN (X1)`.
The slave entered OP with 64-byte input/output PDOs. Patterns `00`, `55`, `AA`,
`FF`, `A5`, and `5A` all passed both paths with WKC `3/3`. The test cleared
outputs and requested SAFE-OP/INIT on exit; RWS then reported both signals as
zero with `valid/good` state.

官方 SOEM v2.0.0 主站通过 `ens6f3` 连接 `ECAT IN (X1)`。从站以 64 字节输入/
输出 PDO 进入 OP。模式 `00`、`55`、`AA`、`FF`、`A5`、`5A` 在两条路径上全部
通过，WKC 始终为 `3/3`。测试退出时清零输出并请求 SAFE-OP/INIT；随后 RWS 报告
两个信号均为零，状态为 `valid/good`。

## Control Station wire detail / 控制站传输细节

RW `8.1.0+600` requires a braced `control-station-id`, for example
`{12345678-1234-5678-9abc-123456789abc}`. An unbraced UUID returned HTTP 400
and ABB code `-20103`. The CLI normalizes UUID input to the required form.

RW `8.1.0+600` 要求 `control-station-id` 带花括号，例如
`{12345678-1234-5678-9abc-123456789abc}`。不带花括号的 UUID 返回 HTTP 400
和 ABB 错误码 `-20103`；CLI 会把 UUID 输入规范化为所需形式。
