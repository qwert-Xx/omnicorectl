# RAPID 编辑与调试

[English](rapid.md) | 简体中文

`omnicorectl rapid` 为 agent 和操作人员提供无需 GUI 的 RobotWare 8 RAPID
源码检查、编辑、部署、构建、诊断和调试流程。可执行 `omnicorectl rapid --help`
或具体子命令的帮助查看精确参数。

## 安全编辑流程

默认的整模块编辑流程如下：

```text
读取源码与 change count
  -> 在本地校验 UTF-8、尺寸、MODULE 名称和 ENDMODULE
  -> 显示 unified diff
  -> 确认 RAPID 已停止
  -> 在有界范围内获取控制站写权限
  -> 再次校验 change count
  -> 使用隐式 RAPID Mastership 写入
  -> 链接任务并读取控制器构建错误
  -> 如果有诊断信息，恢复原源码并重新构建
  -> 即使操作失败也释放写权限
```

`--allow-running`、`--no-build`、`--no-rollback` 和 `--allow-rename` 会分别
放宽安全保护，必须显式指定。`--dry-run` 只执行本地校验并显示差异，不申请写权限。
自动化调用应使用 `--if-change-count N` 拒绝过期修改。

```bash
# 使用 JSON 读取源码和元数据，或只把源码写到标准输出。
omnicorectl rapid read T_ROB1 MainModule --json
omnicorectl rapid read T_ROB1 MainModule > MainModule.mod
omnicorectl rapid validate MainModule.mod --expected-module MainModule --json

# 先预览，再应用同一个文件。
omnicorectl rapid write T_ROB1 MainModule MainModule.mod --dry-run
omnicorectl rapid write T_ROB1 MainModule MainModule.mod \
  --if-change-count 421455 --backup MainModule.before.mod --yes

# 使用交互式编辑器。
EDITOR='code --wait' omnicorectl rapid edit T_ROB1 MainModule --yes

# 替换源码范围，或在范围前后插入。
omnicorectl rapid patch T_ROB1 MainModule 8 1 8 40 \
  --mode After --text '    ! reviewed' --yes
```

## 模块与程序生命周期

`deploy` 组合文件上传、模块加载、任务链接、构建诊断、失败恢复和暂存文件清理。
`load` 用于加载已经存在于控制器文件系统中的文件。

```bash
omnicorectl rapid deploy T_ROB1 ./MainModule.mod --replace --yes
omnicorectl rapid load T_ROB1 '$HOME/MainModule.modx' --replace --yes
omnicorectl rapid save T_ROB1 MainModule '$HOME' --name MainModule --yes
omnicorectl rapid unload T_ROB1 MainModule --yes
omnicorectl rapid build T_ROB1 --yes
omnicorectl rapid errors T_ROB1 --json

omnicorectl rapid program info T_ROB1 --json
omnicorectl rapid program load T_ROB1 '$HOME/application.pgf' --replace --yes
omnicorectl rapid program save T_ROB1 '$HOME/application' --yes
omnicorectl rapid program set-name T_ROB1 Production --yes
omnicorectl rapid program set-entrypoint T_ROB1 main --yes
omnicorectl rapid program unload T_ROB1 --yes
```

## 源码导航与在线数据

```bash
omnicorectl rapid module-info T_ROB1 MainModule --json
omnicorectl rapid read-range T_ROB1 MainModule 1 1 20 -1
omnicorectl rapid search T_ROB1 MainModule MoveL --json

omnicorectl rapid symbol search RAPID/T_ROB1 --symbol-type per --json
omnicorectl rapid symbol get RAPID/T_ROB1/MainModule/counter --json
omnicorectl rapid symbol validate T_ROB1 num 42
omnicorectl rapid symbol set RAPID/T_ROB1/MainModule/counter 42 --yes
omnicorectl rapid symbol set RAPID/T_ROB1/MainModule/counter 42 \
  --initial-value --log --yes

omnicorectl rapid sync-pers-status T_ROB1 MainModule --json
omnicorectl rapid sync-pers T_ROB1 MainModule --yes

omnicorectl rapid motion mechunits T_ROB1 --json
omnicorectl rapid motion robtarget T_ROB1 --tool tool0 --work-object wobj0 --json
omnicorectl rapid motion jointtarget T_ROB1 --json
```

RAPID 值按 RAPID 字面量发送，不是 JSON。例如字符串需要符合 RAPID 的引号规则，
结构值使用 RAPID 的方括号表示法。

## 执行与调试

以下命令能够改变程序执行状态，需要 `--yes` 和对应的控制器权限。启动 RAPID 或移动
程序指针可能根据已加载程序和控制器状态引发机器人运动，执行前必须检查工作站现场。

```bash
omnicorectl rapid execution --json
omnicorectl rapid stop --mode stop --yes
omnicorectl rapid start --mode continue --cycle asis --yes
omnicorectl rapid start --mode stepover --cycle once --yes
omnicorectl rapid reset-pp --yes

omnicorectl rapid pp list T_ROB1 --json
omnicorectl rapid pp cursor T_ROB1 MainModule 12 3 --yes
omnicorectl rapid pp routine T_ROB1 MainModule main --yes
omnicorectl rapid pp next T_ROB1 --yes
omnicorectl rapid pp previous T_ROB1 --yes
omnicorectl rapid pp reset T_ROB1 --yes

omnicorectl rapid breakpoint list T_ROB1 --json
omnicorectl rapid breakpoint set T_ROB1 MainModule 12 3 --yes
omnicorectl rapid breakpoint clear T_ROB1 MainModule 12 3 --yes
omnicorectl rapid breakpoint clear T_ROB1 --all --yes
```

在 RobotWare 8.1 上，`rapid start` 会在写权限作用域内临时启用并回读确认控制站
Motion Control。启动请求结束后，即使请求失败，也会再次关闭并确认 Motion Control。
已认证用户仍需具备相应的 RAPID 执行权限和自动模式远程启停权限，控制器也必须已启用
外部控制。

`modify-position` 使用机器人的当前位置更新运动目标，并有额外的 RobotWare 前置条件。
`write`、`edit` 或 `deploy` 绝不会隐式调用它。

```bash
omnicorectl rapid modifiable-positions T_ROB1 MainModule 10 1 30 80 --json
omnicorectl rapid modify-position T_ROB1 MainModule 15 1 15 80 --yes
omnicorectl rapid activate-task T_ROB1 --yes
omnicorectl rapid deactivate-task T_ROB1 --yes
```

## 退出行为

- 退出码 `0`：操作成功完成。
- 退出码 `2`：本地参数、确认、源码校验或并发检查失败。
- 退出码 `3` 至 `6`：网络、认证、授权、协议或控制器错误。
- 退出码 `7`：`rapid build` 已完成，但控制器报告了构建错误。

除原始源码输出外，所有读取和修改结果都支持 `--json`。构建诊断包含模块、行、列、
可用时的错误编号以及控制器消息。

端点契约基于 ABB 的
[RAPID Service OpenAPI](https://developercenter.robotstudio.com/api/RWS/Swagger_Doc/RAPID_Service.yaml)，
并使用 OmniCore RobotWare 8.1 控制器进行核对。解析器兼容已知 RW8.1 差异，例如
`cycle` 与 `rapidexeccycle`、控制器使用的 `begin-coloumn` 拼写，以及用嵌套错误链接
表示不可用程序指针的响应。

## 明确边界与剩余扩展

当前命令已经完成 agent 常用的源码拉取、受保护编辑、部署、控制器构建诊断、失败
恢复、在线数据查看、断点、单步和程序指针控制闭环，但不宣称封装了庞大的 RAPID
RWS 服务中的每一个端点。仍可继续扩展的高级能力包括：

- 多模块工作区导出，以及在一个事务中同步多个模块；目前可逐模块读取和部署，也可
  通过控制器程序文件整体保存和加载；
- WebSocket 事件订阅和 RAPID Spy 跟踪流；当前命令返回状态快照，调用方可自行轮询；
- 例程参数、对象树、扩展符号属性、指令规则元数据和首选数据类型查询；
- 从生产入口启动、任务面板选择、hold-to-run 控制、中止当前执行层，以及程序/运动
  指针同步记录；
- UI 指令交互、服务例程发现、外部轴状态、托盘、激活记录和标定辅助命令；
- 离线语义编译器或格式化器。本地校验只检查结构，最终以 RobotWare 任务构建为准。

这些项目会明确记录，不使用不稳定或未公开请求进行模拟；当具体 agent 工作流需要时，
可以继续增加对应的类型化命令。
