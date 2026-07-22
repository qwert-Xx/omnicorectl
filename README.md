# omnicorectl

`omnicorectl` is a command-line client for ABB OmniCore controllers using Robot
Web Services (RWS) 2.0.

The project is intentionally independent of RobotStudio and ABB PC SDK. It is
being developed against an OmniCore controller running RobotWare 8.1.

## Current status

The repository has been initialized and its architecture is documented in
[`docs/architecture.md`](docs/architecture.md). Commands will be added in small,
independently tested commits.

## Security rules

- Passwords are read from a prompt or `OMNICORE_PASSWORD`; they are never stored
  in project configuration.
- TLS verification is enabled by default. Controllers with the factory
  self-signed certificate require an explicit `--insecure` option.
- Proxy environment variables are ignored for controller traffic.
- Mutating commands will be visually distinct from read-only commands and will
  use explicit write-access lifecycles.

