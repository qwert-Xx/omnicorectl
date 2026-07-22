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
- Mutating commands will be visually distinct from read-only commands and will
  use explicit write-access lifecycles.
