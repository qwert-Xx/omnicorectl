# RobotWare 8 Control Station lifecycle / RobotWare 8 控制站生命周期

Mutating RWS operations on the target RobotWare 8.1 controller use a Control
Station instead of the deprecated `/rw/mastership` workflow.

目标 RobotWare 8.1 控制器上的 RWS 修改操作使用控制站，而不是已弃用的
`/rw/mastership` 工作流。

`ControlStationService.write_access()` implements this lifecycle:

`ControlStationService.write_access()` 实现以下生命周期：

1. Register a remote Control Station in the authenticated cookie session.
   在已认证的 Cookie 会话中注册远程控制站。
2. Request write access.
   请求写权限。
3. Read status and verify that this exact station is the holder.
   读取状态，并确认当前控制站正是权限持有者。
4. Execute one bounded operation.
   执行一个有界操作。
5. Release write access in `finally`.
   在 `finally` 中释放写权限。
6. Log out and close the RWS session.
   注销并关闭 RWS 会话。

Registration uses `/rw/controlstation/register/remote` with:

注册请求发送至 `/rw/controlstation/register/remote`，字段如下：

```text
control-station-name=<display name / 显示名称>
control-station-id={<UUID with dashes / 带连字符的 UUID>}
pincode=<client-selected numeric PIN / 客户端选择的数字 PIN>
release-write-access-when-lost=true
```

RobotWare 8.1 requires GUID braces on the wire. Sending the same UUID without
braces returned internal code `-20103` (`Control station id not allowed`). The
Python model accepts a normal UUID and adds braces only during ABB form encoding.

RobotWare 8.1 要求传输的 GUID 带花括号。同一 UUID 不带花括号时会返回内部错误码
`-20103`（`Control station id not allowed`）。Python 模型接受普通 UUID，仅在编码
ABB 表单时添加花括号。

The PIN is selected by the registering client; it is not a controller password
and is not discovered from the pendant. It must not be committed to Git.
External control must already be enabled. After requesting access, the service
verifies both the enabled flag and holder UUID before running the operation.

PIN 由注册客户端自行选择，不是控制器密码，也不是从示教器查找出来的值。PIN 不得
提交到 Git。控制器必须预先启用外部控制；请求权限后，服务会同时验证启用标志和
持有者 UUID，然后才执行受保护操作。

Unit tests deliberately raise inside the protected block and assert that release
is still the next RWS call. The acquire/verify/release sequence has also been
verified against the connected real controller.

单元测试会故意在受保护代码块内抛出异常，并确认下一次 RWS 调用仍然是释放权限。
获取、验证、释放的完整顺序也已经在所连接的真实控制器上验证。
