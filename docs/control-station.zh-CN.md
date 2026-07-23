# RobotWare 8 控制站生命周期

[English](control-station.md) | 简体中文

目标 RobotWare 8.1 控制器上的 RWS 修改操作使用控制站，而不是已弃用的
`/rw/mastership` 工作流。

`ControlStationService.write_access()` 实现以下生命周期：

1. 在已认证的 Cookie 会话中注册远程控制站。
2. 请求写权限。
3. 读取状态，并确认当前控制站正是权限持有者。
4. 执行一个有界操作。
5. 在 `finally` 中释放写权限。
6. 注销并关闭 RWS 会话。

注册请求发送至 `/rw/controlstation/register/remote`，字段如下：

```text
control-station-name=<显示名称>
control-station-id={<带连字符的 UUID>}
pincode=<客户端选择的数字 PIN>
release-write-access-when-lost=true
```

RobotWare 8.1 要求传输的 GUID 带花括号。同一 UUID 不带花括号时会返回内部错误码
`-20103`（`Control station id not allowed`）。Python 模型接受普通 UUID，仅在编码
ABB 表单时添加花括号。

PIN 由注册客户端自行选择，不是控制器密码，也不是从示教器查找出来的值。PIN 不得
提交到 Git。控制器必须预先启用外部控制；请求权限后，服务会同时验证启用标志和
持有者 UUID，然后才执行受保护操作。

单元测试会故意在受保护代码块内抛出异常，并确认下一次 RWS 调用仍然是释放权限。
获取、验证、释放的完整顺序也已经在所连接的真实控制器上验证。
