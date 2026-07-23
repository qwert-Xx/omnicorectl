# RobotWare 8 Control Station lifecycle

English | [简体中文](control-station.zh-CN.md)

Mutating RWS operations on the target RobotWare 8.1 controller use a Control
Station instead of the deprecated `/rw/mastership` workflow.

`ControlStationService.write_access()` implements this lifecycle:

1. Register a remote Control Station in the authenticated cookie session.
2. Request write access.
3. Read status and verify that this exact station is the holder.
4. Execute one bounded operation.
5. Release write access in `finally`.
6. Log out and close the RWS session.

Registration uses `/rw/controlstation/register/remote` with:

```text
control-station-name=<display name>
control-station-id={<UUID with dashes>}
pincode=<client-selected numeric PIN>
release-write-access-when-lost=true
```

RobotWare 8.1 requires GUID braces on the wire. Sending the same UUID without
braces returned internal code `-20103` (`Control station id not allowed`). The
Python model accepts a normal UUID and adds braces only during ABB form encoding.

The PIN is selected by the registering client; it is not a controller password
and is not discovered from the pendant. It must not be committed to Git.
External control must already be enabled. After requesting access, the service
verifies both the enabled flag and holder UUID before running the operation.

Unit tests deliberately raise inside the protected block and assert that release
is still the next RWS call. The acquire/verify/release sequence has also been
verified against the connected real controller.
