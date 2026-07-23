# Architecture

English | [简体中文](architecture.zh-CN.md)

Status: accepted, 2026-07-22

## Goals

`omnicorectl` is a Linux-friendly CLI for inspecting and administering ABB
OmniCore controllers through RWS 2.0. Its first target is RobotWare 8.1, while
the protocol code tolerates additive fields and minor RobotWare differences.

Important constraints include controller sessions, explicit media types,
factory self-signed certificates, the documented request-rate limit, and the
RobotWare 8 Control Station/write-access workflow. Commands must not leak
credentials or leave write access held after exit.

## Language convention

English and Simplified Chinese documentation are stored in separate files.
English files use the `.md` suffix; Chinese counterparts use `.zh-CN.md`.
Maintainer-facing docstrings, meaningful code comments, and explicit CLI help
contain both languages because they live next to executable code rather than in
standalone documents.

Protocol field names, code identifiers, machine-readable JSON keys, controller
payloads, and test fixtures remain unchanged so wire behavior stays stable.

## Projects reviewed

### ABB RWS OpenAPI

Sources:

- <https://robotwebservices.robotics.abb.com/>
- <https://developercenter.robotstudio.com/api/RWS>

ABB publishes service-specific OpenAPI 3 definitions. They are authoritative
for paths, verbs, form fields, media types, and examples. They are not a runtime
dependency and are not blindly generated into this client: the examined RAPID,
I/O, and CFG definitions lack `operationId` values and reusable response
schemas, while RWS returns dynamic HAL+JSON or XHTML resources. Online docs can
also lag controller behavior, so live read-only probes and controller responses
serve as additional compatibility evidence.

Decision: keep endpoint mapping explicit and traceable to OpenAPI. A future
development-time checker may compare endpoint declarations with ABB specs.

### `abb_robot_client` (Python)

Source: <https://github.com/rpiRobotics/abb_robot_client>

This project validates the usefulness of one session boundary and typed domain
results. Its RWS implementation targets RobotWare 6 and explicitly excludes
RobotWare 7+, and its synchronous/asynchronous implementations duplicate much
endpoint logic.

Decision: use a central session and typed results, target RWS 2.0 only, and
start synchronously. Add an asynchronous surface only for a demonstrated need.

### `abb_librws` (C++)

Source: <https://github.com/ros-industrial/abb_librws>

Its separation of HTTP, general RWS operations, RAPID helpers, configuration,
and higher-level workflows is valuable. Its C++/Poco/ROS stack and older-RWS
focus are unnecessarily heavy for this portable administration CLI.

Decision: retain the protocol/workflow separation without adopting its runtime
stack or state-machine specialization.

### `abb-rws-client` and ABB Robot VS Code extension (TypeScript)

Sources:

- <https://github.com/ichbinmeraj/abb-rws-vscode>
- <https://www.npmjs.com/package/abb-rws-client>

This reference separates HTTP sessions, parsers, resource mapping, version
adapters, subscriptions, and the higher-level robot manager. It also covers
throttling, cookies, cleanup, polling fallback, and typed errors, while keeping
UI concerns outside the protocol layer.

Decision: adopt the broad separation of concerns, but omit version adapters and
a permanently polling manager because this short-lived CLI deliberately targets
OmniCore/RWS 2.0 only. Every invocation owns and deterministically closes one
bounded session.

## Chosen stack

- Python 3.10 or newer.
- `httpx` for Basic authentication, cookies, explicit timeouts, streaming, and
  injectable mock transports.
- Standard-library `argparse` for a dependency-light command tree.
- `dataclasses` and tolerant mapping parsers rather than strict validation, so
  additive ABB fields do not break clients.
- `unittest` and `httpx.MockTransport` for deterministic protocol tests; live
  controller checks remain explicit integration tests.

## Layers

```text
CLI commands
    -> application services (controller, rapid, io, cfg, files, backup)
        -> RWS endpoint client and parsers
            -> HTTP transport/session
                -> OmniCore controller
```

Current package layout:

```text
src/omnicorectl/
  cli.py                 argument parsing, exit codes, output selection
  rapid_cli.py           RAPID command tree and guarded CLI workflows
  errors.py              user-facing exception hierarchy
  output.py              table, JSON, and raw output
  rws/
    hal.py               tolerant HAL+JSON parsing
    client.py            HTTPS session, throttling, streaming, errors
  services/
    controller.py        status and lifecycle
    rapid.py             source, module, program, and task primitives
    rapid_debug.py       execution, pointers, breakpoints, and symbols
    rapid_editing.py     checked editing, deployment, build, and rollback
    io.py                networks, devices, signals
    cfg.py               guarded configuration mutation
    control_station.py   RW8 write-access lifecycle
    files.py             file operations and path guards
    backup.py            asynchronous backup lifecycle
```

Configuration resolution remains in `cli.py`; HTTPS transport and error parsing
share one boundary in `rws/client.py`. Split them only when an independent
consumer appears, avoiding empty modules and pass-through abstractions.

## Command contract

- Nouns form groups: `controller`, `rapid`, `io`, `cfg`, `file`, `backup`, and
  `controlstation`.
- Verbs describe one operation: `status`, `list`, `get`, `set`, `create`, and
  `delete`.
- Read commands default to concise text and support `--json`.
- Source and file bytes go to stdout or an explicit file; diagnostics go to
  stderr.
- Exit `0` means success; `2` means CLI/configuration error; other stable codes
  distinguish authentication, authorization, network, and RWS failures.
- Reads never mutate implicitly.
- Write access is released in `finally`, including after errors and interrupts.

The verified Control Station lifecycle is documented in
[`control-station.md`](control-station.md).
The RAPID editing transaction and command surface are documented in
[`rapid.md`](rapid.md).

```bash
OMNICORE_PASSWORD=... omnicorectl \
  --host 192.168.125.1 --username codex --insecure \
  controller status --json
```

`--password` is intentionally absent because process arguments and shell history
can expose it. Without the environment variable, an interactive prompt is used.

## Testing strategy

Each feature commit includes, as applicable:

1. parser/service unit tests with sanitized response shapes;
2. CLI output and exit tests;
3. a read-only live check against the connected RW8.1 controller;
4. for writes, pre-read, scoped mutation, readback, and guaranteed access release;
5. no credentials, cookies, backups, or generated local profiles in Git.

Live tests require physical hardware and are excluded from the default unit
suite. Sanitized results are recorded in
[`live-validation.md`](live-validation.md).

## Deferred decisions

- WebSocket subscriptions wait for a `watch` use case.
- Multi-controller orchestration and named profiles are deferred.
- RWS 1.0/IRC5 is out of scope; any future support belongs in a protocol adapter,
  not scattered conditionals.
- OpenAPI generation remains development tooling until generated code is clearer
  and better tested than explicit mappings.
