# RAPID editing and debugging

English | [简体中文](rapid.zh-CN.md)

`omnicorectl rapid` provides a non-GUI workflow for agents and operators to
inspect, edit, deploy, build, diagnose, and debug RAPID code on RobotWare 8.
Run `omnicorectl rapid --help` or the help of any nested command for the exact
arguments.

## Safe editing workflow

The default complete-module workflow is:

```text
read source and change count
  -> validate UTF-8, size, MODULE name, and ENDMODULE locally
  -> show a unified diff
  -> verify RAPID is stopped
  -> acquire bounded Control Station write access
  -> verify the change count again
  -> write with implicit RAPID Mastership
  -> link the task and read controller build errors
  -> restore the original source and rebuild if diagnostics are returned
  -> release write access even when an operation fails
```

`--allow-running`, `--no-build`, `--no-rollback`, and `--allow-rename` weaken
individual guards and must be selected explicitly. `--dry-run` performs local
validation and displays the diff without requesting write access. Use
`--if-change-count N` in automation to reject stale edits.

```bash
# Checkout with metadata in JSON, or source only through stdout.
omnicorectl rapid read T_ROB1 MainModule --json
omnicorectl rapid read T_ROB1 MainModule > MainModule.mod
omnicorectl rapid validate MainModule.mod --expected-module MainModule --json

# Preview and then apply the same file.
omnicorectl rapid write T_ROB1 MainModule MainModule.mod --dry-run
omnicorectl rapid write T_ROB1 MainModule MainModule.mod \
  --if-change-count 421455 --backup MainModule.before.mod --yes

# Use an interactive editor.
EDITOR='code --wait' omnicorectl rapid edit T_ROB1 MainModule --yes

# Replace, insert before, or insert after a source range.
omnicorectl rapid patch T_ROB1 MainModule 8 1 8 40 \
  --mode After --text '    ! reviewed' --yes
```

## Module and program lifecycle

`deploy` combines file upload, module loading, task linking, build diagnostics,
rollback, and staging-file cleanup. `load` operates on a file that already
exists in the controller file system.

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

## Source navigation and online data

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

RAPID values are sent as RAPID literals, not JSON. For example, strings need
RAPID quoting and structured values use their RAPID bracket notation.

## Execution and debugging

The commands below can alter program execution. They require `--yes` and the
controller permissions appropriate to the operation. Starting RAPID or moving a
program pointer can cause robot motion depending on the loaded program and
controller state; inspect the workcell before running them.

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

On RobotWare 8.1, `rapid start` temporarily enables and verifies Control
Station Motion Control inside the write-access scope. It always disables and
verifies Motion Control again after the start request, including when that
request fails. The authenticated user still needs the relevant RAPID execution
and remote start/stop grants, and external control must be enabled.

`modify-position` updates a motion target from the robot's current position and
has additional RobotWare preconditions. It is intentionally never invoked by
`write`, `edit`, or `deploy`.

```bash
omnicorectl rapid modifiable-positions T_ROB1 MainModule 10 1 30 80 --json
omnicorectl rapid modify-position T_ROB1 MainModule 15 1 15 80 --yes
omnicorectl rapid activate-task T_ROB1 --yes
omnicorectl rapid deactivate-task T_ROB1 --yes
```

## Exit behavior

- Exit `0`: operation completed successfully.
- Exit `2`: local arguments, confirmation, source validation, or concurrency
  check failed.
- Exit `3` through `6`: network, authentication, authorization, protocol, or
  controller failure.
- Exit `7`: `rapid build` completed but the controller reported build errors.

All read and mutation results support `--json` except raw source output. Build
diagnostics include module, row, column, error number when available, and the
controller message.

The endpoint contract is based on ABB's
[RAPID Service OpenAPI](https://developercenter.robotstudio.com/api/RWS/Swagger_Doc/RAPID_Service.yaml)
and is checked against an OmniCore RobotWare 8.1 controller. The parser accepts
known RW8.1 differences such as `cycle` versus `rapidexeccycle`, the controller's
`begin-coloumn` spelling, and unavailable PP resources represented by nested
error links.

## Deliberate scope and remaining extensions

The command set completes the common agent loop of source checkout, guarded
editing, deployment, controller build diagnostics, rollback, online-data
inspection, breakpoints, stepping, and program-pointer control. It does not
claim to wrap every endpoint in the much larger RAPID RWS service. The remaining
advanced extensions are:

- multi-module workspace export and one-transaction synchronization; modules can
  currently be read and deployed individually, or moved as a complete controller
  program;
- WebSocket event subscriptions and RAPID Spy trace streaming; current commands
  return snapshots and can be polled by the caller;
- routine arguments, object trees, extended symbol properties, instruction-rule
  metadata, and preferred-data-type introspection;
- production-entry startup, task-panel selection, hold-to-run control, execution
  level abort, and program/motion-pointer synchronization records;
- UI-instruction interaction, service-routine discovery, external-joint state,
  pallet, activation-record, and calibration helpers;
- an offline semantic compiler or formatter. Local validation is structural;
  RobotWare's task build remains authoritative.

These are intentionally documented instead of being simulated through unstable
or undocumented requests. They can be added as typed commands when an agent
workflow needs them.
