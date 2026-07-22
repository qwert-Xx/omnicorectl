# RobotWare 8 Control Station lifecycle

Mutating RWS operations on the target RobotWare 8.1 controller use a Control
Station rather than the deprecated `/rw/mastership` workflow.

The lifecycle implemented by `ControlStationService.write_access()` is:

1. register a remote Control Station in the current authenticated cookie session;
2. request write access;
3. read status and verify that this exact station is the holder;
4. execute one bounded operation;
5. release write access in `finally`;
6. let the RWS client log out and close the session.

The registration form is sent to `/rw/controlstation/register/remote` with:

```text
control-station-name=<display name>
control-station-id={<UUID with dashes>}
pincode=<client-selected numeric PIN>
release-write-access-when-lost=true
```

RobotWare 8.1 specifically requires the GUID braces on the wire. Sending the
same UUID without braces was rejected with controller internal code `-20103`,
"Control station id not allowed". The public Python model accepts a normal UUID
string and adds the braces only when encoding the ABB form.

The PIN is not a controller password and is not discovered from the pendant; it
is selected by the registering client. It must still not be persisted in Git.
External control must already be enabled on the controller. After requesting
access, the implementation verifies both the enabled flag and holder UUID before
allowing the protected operation to run.

Unit tests deliberately raise inside the protected block and assert that release
is still the next RWS call. The same acquire/verify/release sequence has also
been verified against the connected real controller without modifying RAPID,
I/O, or CFG data.
