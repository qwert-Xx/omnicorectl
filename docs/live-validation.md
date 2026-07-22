# Live-controller validation

This file records sanitized integration evidence that is intentionally excluded
from the deterministic unit suite. It contains no passwords, PINs, cookies, or
controller backup contents.

## Target

- Validation date: 2026-07-22
- Controller: OmniCore V250XT, real controller
- RobotWare: `8.1.0+600`
- RWS endpoint: HTTPS on the controller service port
- RWS representation: `application/hal+json;v=2.0`

## Read-only coverage

The installed CLI successfully read:

- controller identity, operation mode, controller state, and RAPID state;
- RAPID tasks, module inventory, and module source;
- I/O networks, devices, signal inventory, and detailed signal state;
- CFG domains, types, instances, and detailed attributes;
- controller file directories and files;
- backup engine state;
- RW8 Control Station/write-access status.

The final preflight observed RAPID stopped, the backup engine in `Backup Ready`,
external control enabled, and no Control Station holding write access. The
controller was in emergency-stop state, so backup creation, CFG mutation, and
warm restart were deliberately not triggered during the final audit.

## Reversible write coverage

A unique probe under `$TEMP` exercised the complete file workflow:

1. registered a remote RW8 Control Station;
2. acquired and verified scoped write access;
3. uploaded the repository `README.md` as a binary file;
4. released write access;
5. downloaded the probe through a separate CLI invocation;
6. compared source and download SHA-256 hashes byte-for-byte;
7. reacquired scoped write access and deleted the remote probe;
8. confirmed the probe no longer appeared under `$TEMP`;
9. confirmed final write-access status was `held=false` with holder `none`.

Both hashes were identical. The probe was removed from the controller. A later
safety hardening added a directory preflight to `file delete`; its protocol and
refusal paths are covered by the unit suite.

## Control Station wire detail

RW `8.1.0+600` requires `control-station-id` to be sent as a braced GUID such as
`{12345678-1234-5678-9abc-123456789abc}`. An unbraced UUID returned HTTP 400
with ABB internal code `-20103` (`Control station id not allowed`). The CLI
normalizes UUID input to the required braced representation.
