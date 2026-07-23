# Live-controller validation

English | [简体中文](live-validation.zh-CN.md)

This file records sanitized integration evidence excluded from the deterministic
unit suite. It contains no passwords, PINs, cookies, or backup contents.

## Target

- Validation dates: 2026-07-22 and 2026-07-23
- Controller: real OmniCore V250XT
- RobotWare: `8.1.0+600`
- RWS endpoint: controller HTTPS service port
- Representation: `application/hal+json;v=2.0`

## Read-only coverage

The installed CLI successfully read:

- controller identity, operation mode, controller state, and RAPID state;
- RAPID tasks, module inventory, module source, execution state, module
  attributes and dimensions, source ranges, text search, build diagnostics,
  SyncPers status, breakpoints, symbols, and online symbol data;
- I/O networks, devices, signal inventory, and detailed signal state;
- CFG domains, types, instances, and attributes;
- file directories and files, backup state, and Control Station status.

The completion preflight observed RAPID stopped, backup state `Backup Ready`,
external control enabled, and no station holding write access. The controller
was in emergency stop during the audit.

The expanded RAPID read/debug surface was rechecked on 2026-07-23. The RW8.1
controller uses `cycle` in the execution-state payload, spells source-position
columns as `begin-coloumn`/`end-coloumn`, and returns nested error links when no
program pointer exists. Compatibility handling and sanitized fixtures cover all
three shapes. No execution start, program-pointer movement, target modification,
or robot motion was performed during this read-only validation.

## Reversible file write

A unique `$TEMP` probe exercised this workflow:

1. register a remote Control Station;
2. acquire and verify scoped write access;
3. upload `README.md` as binary data;
4. release access;
5. download through another CLI invocation;
6. compare SHA-256 byte-for-byte;
7. reacquire access, delete, and confirm absence;
8. verify final status `held=false`, holder `none`.

The completion audit repeated the workflow after adding the ordinary-file delete
guard. A 4,806-byte probe passed upload, download, hash comparison, parent-path
preflight, type verification, deletion, and absence verification. Its SHA-256 was
`94d05228aff4f9d3de5725b91c8b94b229cc3e5b34fc5822ff15213085c101eb`.

## Reversible RAPID editing

A temporary module with one never-invoked, non-motion routine exercised the
complete editing path on 2026-07-23:

1. upload to `$TEMP`, load into `T_ROB1`, link, and confirm no build errors;
2. read back the exact module source and find its routine through symbol search;
3. replace the complete module text with a change-count guard;
4. read back the exact requested text, link, and confirm no build errors;
5. replace one source range, read it back, link, and confirm no build errors;
6. read and update a temporary `PERS num`, then verify the online value;
7. set, list, clear, and re-list a breakpoint on a never-executed assignment;
8. unload the probe, link again, and verify the original module inventory;
9. verify the staging upload was removed and Control Station access was released.

The observed change count advanced by one for both the complete write and range
patch. The probe had no entry point, was never executed, and contained no motion
instruction. No permanent RAPID or file-system artifact remained afterward.

## CFG and EtherCAT I/O

The CFG create workflow created and validated two external signals plus Cross
Data and Transfer Data instances. A normal warm restart activated them:

| Type | Instance | Mapping |
|---|---|---|
| `EIO_SIGNAL` | `EtherCAT_DI` | DI, `EC_Internal_Device`, input bit 0 |
| `EIO_SIGNAL` | `EtherCAT_DO` | DO, `EC_Internal_Device`, output bit 0 |
| `EIO_CROSS` | `EtherCAT_CrossLoopback` | `EtherCAT_DI` → `EtherCAT_DO` |
| `EIO_DEVICE_TRANSFER_DATA` | `EtherCAT_RawLoopback` | input bits 8–15 → output bits 8–15 |

An official SOEM v2.0.0 master connected through `ens6f3` to `ECAT IN (X1)`.
The slave entered OP with 64-byte input/output PDOs. Patterns `00`, `55`, `AA`,
`FF`, `A5`, and `5A` all passed both paths with WKC `3/3`. The test cleared
outputs and requested SAFE-OP/INIT on exit; RWS then reported both signals as
zero with `valid/good` state.

## Control Station wire detail

RW `8.1.0+600` requires a braced `control-station-id`, for example
`{12345678-1234-5678-9abc-123456789abc}`. An unbraced UUID returned HTTP 400
and ABB code `-20103`. The CLI normalizes UUID input to the required form.
