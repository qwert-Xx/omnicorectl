# Architecture

Status: accepted, 2026-07-22

## Goals

`omnicorectl` is a Linux-friendly CLI for inspecting and administering ABB
OmniCore controllers through RWS 2.0. Its first target is RobotWare 8.1, but the
protocol code must tolerate additive fields and minor RobotWare differences.

The important constraints are controller sessions, explicit content types,
factory self-signed certificates, a maximum documented request rate, and the
RobotWare 8 Control Station/write-access workflow. A command must not leak
credentials or leave write access held after it exits.

## Projects reviewed

### ABB RWS OpenAPI

Sources:

- <https://robotwebservices.robotics.abb.com/>
- <https://developercenter.robotstudio.com/api/RWS>

ABB publishes OpenAPI 3 descriptions split by service. They are authoritative
for paths, verbs, form fields, media types, and examples. They are not used as a
runtime dependency or blindly generated into the client because the examined
RAPID, I/O, and CFG documents have no `operationId` values or reusable response
schemas. RWS returns dynamic HAL+JSON or XHTML resources, and the online
documents can lag controller behavior. Controller `OPTIONS` responses and live
read-only probes are therefore compatibility evidence alongside OpenAPI.

Decision: keep endpoint mapping explicit and traceable to OpenAPI. We may later
add a development-time checker that compares our endpoint declarations with
ABB's specifications.

### `abb_robot_client` (Python)

Source: <https://github.com/rpiRobotics/abb_robot_client>

This client provides synchronous and asynchronous RWS implementations plus EGM.
It centralizes HTTP calls in a session and converts controller resources to
typed tuples. That validates the value of a small transport boundary and typed
domain results. Its RWS implementation targets RobotWare 6 and explicitly does
not support RobotWare 7+, while its sync and async implementations duplicate a
large amount of endpoint logic.

Decision: adopt a central session and typed results, but target only RWS 2.0 and
start with a synchronous API. Do not maintain parallel sync/async surfaces until
a real use case justifies them.

### `abb_librws` (C++)

Source: <https://github.com/ros-industrial/abb_librws>

This library separates the HTTP client, general RWS interface, RAPID helpers,
configuration types, and higher-level state-machine interface. This keeps
protocol mechanics out of robot workflows, but its C++/Poco/ROS-oriented stack
is unnecessarily heavy for a portable administration CLI and targets older RWS.

Decision: retain its separation between protocol primitives and operational
workflows without adopting its runtime stack or state-machine specialization.

### `abb-rws-client` / ABB Robot VS Code extension (TypeScript)

Sources:

- <https://github.com/ichbinmeraj/abb-rws-vscode>
- <https://www.npmjs.com/package/abb-rws-client>

This is the strongest architectural reference examined. It separates HTTP
session management, response parsers, resource mapping, RWS-version adapters,
WebSocket subscriptions, and a higher-level robot manager. It also accounts for
request throttling, cookie reuse, session cleanup, polling fallback, and typed
errors. The associated extension keeps UI concerns outside the protocol layer.

Decision: use the same broad separation of concerns, but avoid a version-adapter
abstraction because `omnicorectl` deliberately supports OmniCore/RWS 2.0 only.
Avoid a permanently polling manager in a short-lived CLI. Each invocation owns
one bounded session and closes it deterministically.

## Chosen stack

- Python 3.10 or newer.
- `httpx` for Basic authentication, cookie persistence, explicit timeouts,
  streaming, and an injectable mock transport.
- Standard-library `argparse` for the command tree. It keeps the executable
  dependency-light and stable; terminal rendering does not belong in protocol
  code.
- Standard-library `dataclasses` and tolerant mapping parsers instead of a
  strict validation framework. ABB may add fields without breaking clients.
- Standard-library `unittest` plus `httpx.MockTransport` for deterministic
  protocol tests. Live-controller checks remain explicit integration tests.

## Layers

```text
CLI commands
    -> application services (controller, rapid, io, cfg, backup)
        -> RWS endpoint client and HAL/XHTML parsers
            -> HTTP transport/session
                -> OmniCore controller
```

Planned package layout:

```text
src/omnicorectl/
  cli.py                 argument parsing, exit codes, output selection
  config.py              environment/profile resolution, no stored passwords
  errors.py              stable user-facing exception hierarchy
  output.py              table, JSON, and raw output
  rws/
    transport.py         HTTPS, Basic auth, cookies, timeout, rate limit
    hal.py               tolerant HAL+JSON parsing
    xhtml.py             fallback/error parsing
    client.py            generic request boundary and error translation
  services/
    controller.py        status and controller lifecycle
    rapid.py             tasks, modules, source, execution
    io.py                networks, devices, signals
    cfg.py               configuration database
    control_station.py   RW8 registration/write-access context manager
    backup.py            async backup lifecycle and download
```

The layout is evolutionary: directories are created when the first real module
needs them, not as empty placeholders.

## Command contract

- Nouns form command groups: `controller`, `rapid`, `io`, `cfg`, `backup`.
- Verbs describe one operation: `status`, `list`, `get`, `set`, `create`.
- Read commands default to concise human output and support `--json`.
- Commands that return source or file bytes write raw data to stdout or an
  explicitly named file; diagnostics go to stderr.
- Exit code `0` means success, `2` means CLI/configuration error, and other
  stable codes will distinguish authentication, authorization, network, and RWS
  errors.
- Mutating operations never happen as an implicit side effect of a read command.
- A command that obtains write access releases it in `finally`, including after
  errors or interrupts.

Initial invocation shape:

```bash
OMNICORE_PASSWORD=... omnicorectl \
  --host 192.168.125.1 --username codex --insecure \
  controller status --json
```

`--password` is deliberately omitted because command-line arguments are visible
to other local processes and shell history. If the environment variable is not
set, an interactive terminal prompt is used.

## Testing strategy

Every feature commit must include, as applicable:

1. parser/service unit tests using recorded, sanitized response shapes;
2. CLI tests for output and exit behavior;
3. a read-only live check against the connected RW8.1 controller;
4. for writes, a pre-read, scoped change, post-read verification, and guaranteed
   write-access release;
5. no credentials, cookies, controller backups, or generated local profiles in
   Git.

Live tests are not part of the default unit suite because they require physical
hardware. Their exact command and observed RobotWare version are recorded in the
commit or development notes.

## Deferred decisions

- WebSocket subscription support is deferred until `watch` functionality is
  implemented. A short-lived read command should not establish a subscription.
- Multi-controller orchestration is deferred. Named profiles can be added
  without changing the service boundary.
- RWS 1.0/IRC5 compatibility is explicitly out of scope. If it is later needed,
  it should be a protocol adapter rather than conditionals scattered through
  services.
- OpenAPI generation is deferred to development tooling; generated endpoint
  code will not be accepted until its output is clearer and better tested than
  the explicit mapping.

