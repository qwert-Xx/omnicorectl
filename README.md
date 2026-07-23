# omnicorectl

English | [简体中文](README.zh-CN.md)

`omnicorectl` is a command-line client for ABB OmniCore controllers using Robot
Web Services (RWS) 2.0. It is intentionally independent of RobotStudio and ABB
PC SDK, and is developed against an OmniCore controller running RobotWare 8.1.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Controller operations

```bash
export OMNICORE_HOST=192.168.125.1
export OMNICORE_USERNAME=codex
export OMNICORE_PASSWORD='set-this-outside-shell-history'
# Required only by write commands; this is a client-selected numeric PIN.
export OMNICORE_CONTROL_STATION_PIN='set-a-numeric-pin'

# Factory certificates are normally self-signed.
.venv/bin/omnicorectl --insecure controller status
.venv/bin/omnicorectl --insecure controller status --json

# List RAPID tasks without changing execution state.
.venv/bin/omnicorectl --insecure rapid tasks
.venv/bin/omnicorectl --insecure rapid tasks --json

# List modules in a task.
.venv/bin/omnicorectl --insecure rapid modules T_ROB1

# Read module source without modifying it.
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion > EGM_StreamMotion.mod

# Validate and preview a complete-module update without writing.
.venv/bin/omnicorectl --insecure rapid write \
  T_ROB1 EGM_StreamMotion ./EGM_StreamMotion.mod --dry-run

# Write, build, diagnose, and roll back automatically on build failure.
.venv/bin/omnicorectl --insecure rapid write \
  T_ROB1 EGM_StreamMotion ./EGM_StreamMotion.mod --yes

# Open a controller module in $EDITOR with the same guarded workflow.
.venv/bin/omnicorectl --insecure rapid edit T_ROB1 EGM_StreamMotion --yes

# Upload, replace, build, verify, and remove the staging upload.
.venv/bin/omnicorectl --insecure rapid deploy \
  T_ROB1 ./EGM_StreamMotion.mod --replace --yes

# Browse I/O networks, devices, and signals.
.venv/bin/omnicorectl --insecure io networks
.venv/bin/omnicorectl --insecure io devices EtherCAT
.venv/bin/omnicorectl --insecure io signals
.venv/bin/omnicorectl --insecure io signals --network EtherCAT --device EC_Internal_Device
.venv/bin/omnicorectl --insecure io signals --type DI --json

# Read signal state and access metadata.
.venv/bin/omnicorectl --insecure io get SC_Feedback_Net SC_Feedback_Dev SafetyEnable

# Browse controller configuration.
.venv/bin/omnicorectl --insecure cfg domains
.venv/bin/omnicorectl --insecure cfg types EIO
.venv/bin/omnicorectl --insecure cfg instances EIO ETHERCAT_INTERNAL_DEVICE
.venv/bin/omnicorectl --insecure cfg instances EIO EIO_SIGNAL --json
.venv/bin/omnicorectl --insecure cfg get EIO ETHERCAT_INTERNAL_DEVICE EC_Internal_Device

# Update, validate, and re-read one attribute.
.venv/bin/omnicorectl --insecure cfg set EIO EIO_SIGNAL MySignal Label 'new label' --yes

# Create, initialize, validate, and verify an external instance.
.venv/bin/omnicorectl --insecure cfg create EIO EIO_SIGNAL EtherCAT_DI \
  --set SignalType=DI \
  --set Device=EC_Internal_Device \
  --set DeviceMap=0 \
  --yes

# Validate, delete, and verify absence.
.venv/bin/omnicorectl --insecure cfg delete EIO EIO_SIGNAL EtherCAT_DI --yes

# Browse controller files.
.venv/bin/omnicorectl --insecure file list
.venv/bin/omnicorectl --insecure file list '$HOME'

# Download atomically; --force permits replacement.
.venv/bin/omnicorectl --insecure file download '$HOME/sc_vsm_metadata.xml' ./sc_vsm_metadata.xml

# Upload without overwriting by default.
.venv/bin/omnicorectl --insecure file upload ./local.bin '$TEMP/local.bin'

# Permanent deletion requires confirmation.
.venv/bin/omnicorectl --insecure file delete '$TEMP/local.bin' --yes

# Read backup state or create a tar backup.
.venv/bin/omnicorectl --insecure backup status
.venv/bin/omnicorectl --insecure backup create '$TEMP/backup_20260722'

# Inspect external-control/write-access state.
.venv/bin/omnicorectl --insecure controlstation status

# Request only a normal warm restart.
.venv/bin/omnicorectl --insecure controller restart --yes
```

Global connection options must precede the command group. `--host` and
`--username` override their corresponding environment variables.

Architecture and incremental development rules are documented in
[`docs/architecture.md`](docs/architecture.md).
The complete RAPID editing and debugging command reference is in
[`docs/rapid.md`](docs/rapid.md).

## Security rules

- Passwords come from an interactive prompt or `OMNICORE_PASSWORD`; project
  configuration never stores them.
- TLS verification is enabled by default. Factory self-signed certificates
  require an explicit `--insecure` option.
- Controller traffic ignores proxy environment variables.
- Mutating commands use a bounded Control Station write-access lifecycle.
  Destructive operations require confirmation; file and CFG writes include
  guards, validation, readback, or rollback as applicable.
- RAPID source writes use change-count concurrency checks, implicit RAPID
  Mastership, controller-side build diagnostics, and rollback by default.

## Development verification

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
