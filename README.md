# omnicorectl

`omnicorectl` is a command-line client for ABB OmniCore controllers using Robot
Web Services (RWS) 2.0.

The project is intentionally independent of RobotStudio and ABB PC SDK. It is
being developed against an OmniCore controller running RobotWare 8.1.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Controller status

```bash
export OMNICORE_HOST=192.168.125.1
export OMNICORE_USERNAME=codex
export OMNICORE_PASSWORD='set-this-outside-shell-history'
# Required only by write commands; this is a client-selected numeric PIN.
export OMNICORE_CONTROL_STATION_PIN='set-a-numeric-pin'

# Factory OmniCore certificates are normally self-signed.
.venv/bin/omnicorectl --insecure controller status
.venv/bin/omnicorectl --insecure controller status --json

# List RAPID tasks without changing execution state.
.venv/bin/omnicorectl --insecure rapid tasks
.venv/bin/omnicorectl --insecure rapid tasks --json

# List program and system modules in a task.
.venv/bin/omnicorectl --insecure rapid modules T_ROB1

# Read module source without modifying the controller.
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion
.venv/bin/omnicorectl --insecure rapid read T_ROB1 EGM_StreamMotion > EGM_StreamMotion.mod

# List configured I/O networks.
.venv/bin/omnicorectl --insecure io networks

# List devices belonging to one network.
.venv/bin/omnicorectl --insecure io devices EtherCAT

# List all signals or search by controller-side criteria.
.venv/bin/omnicorectl --insecure io signals
.venv/bin/omnicorectl --insecure io signals --network EtherCAT --device EC_Internal_Device
.venv/bin/omnicorectl --insecure io signals --type DI --json

# Read logical/physical state and access metadata for one signal.
.venv/bin/omnicorectl --insecure io get SC_Feedback_Net SC_Feedback_Dev SafetyEnable

# Browse controller configuration domains.
.venv/bin/omnicorectl --insecure cfg domains
.venv/bin/omnicorectl --insecure cfg types EIO
.venv/bin/omnicorectl --insecure cfg instances EIO ETHERCAT_INTERNAL_DEVICE
.venv/bin/omnicorectl --insecure cfg instances EIO EIO_SIGNAL --json
.venv/bin/omnicorectl --insecure cfg get EIO ETHERCAT_INTERNAL_DEVICE EC_Internal_Device

# Update, validate, re-read, and report that a warm restart is required.
.venv/bin/omnicorectl --insecure cfg set EIO EIO_SIGNAL MySignal Label 'new label' --yes

# Create a default external instance, apply all initial attributes in one update,
# validate the final state, and verify it by reading it back. A failed create is
# automatically removed again.
.venv/bin/omnicorectl --insecure cfg create EIO EIO_SIGNAL EtherCAT_DI \
  --set SignalType=DI \
  --set Device=EC_Internal_Device \
  --set DeviceMap=0 \
  --yes

# Validate an external instance for deletion, delete it, and verify absence.
.venv/bin/omnicorectl --insecure cfg delete EIO EIO_SIGNAL EtherCAT_DI --yes

# Browse controller file volumes and directories.
.venv/bin/omnicorectl --insecure file list
.venv/bin/omnicorectl --insecure file list '$HOME'

# Stream a controller file to an atomic local destination; --force allows replacement.
.venv/bin/omnicorectl --insecure file download '$HOME/sc_vsm_metadata.xml' ./sc_vsm_metadata.xml

# Upload defaults to no-overwrite and uses scoped RW8 write access.
.venv/bin/omnicorectl --insecure file upload ./local.bin '$TEMP/local.bin'

# Deletion requires explicit confirmation and the same scoped write access.
.venv/bin/omnicorectl --insecure file delete '$TEMP/local.bin' --yes

# Read the controller backup engine state.
.venv/bin/omnicorectl --insecure backup status

# Create a tar backup, poll its progress, and release write access afterward.
# The safe default refuses if RAPID is running or the destination already exists.
.venv/bin/omnicorectl --insecure backup create '$TEMP/backup_20260722'

# Inspect RW8 external-control and write-access state.
.venv/bin/omnicorectl --insecure controlstation status

# Request only a normal warm restart; destructive restart modes are not exposed.
.venv/bin/omnicorectl --insecure controller restart --yes
```

Global connection options must precede the command group. `--host` and
`--username` override their corresponding environment variables.

The architecture and incremental development rules are documented in
[`docs/architecture.md`](docs/architecture.md).

## Security rules

- Passwords are read from a prompt or `OMNICORE_PASSWORD`; they are never stored
  in project configuration.
- TLS verification is enabled by default. Controllers with the factory
  self-signed certificate require an explicit `--insecure` option.
- Proxy environment variables are ignored for controller traffic.
- Mutating commands use a bounded Control Station write-access lifecycle.
  Destructive operations require explicit confirmation, file operations use
  path/existence guards, and CFG writes use validation plus readback/rollback.

## Development verification

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q src tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy src
.venv/bin/python -m pip wheel --no-deps . --wheel-dir /tmp/omnicorectl-wheel
```

Sanitized checks against the RW 8.1 controller are recorded in
[`docs/live-validation.md`](docs/live-validation.md).
