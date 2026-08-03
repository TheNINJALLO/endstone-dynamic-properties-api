# Endstone Dynamic Properties API Tester

This is the operator-only, CPython 3.14 acceptance wheel for Dynamic
Properties API `0.1.0a5` on Endstone `0.11.6`. The wheel loads only its
package-local `_endstone_dynamic_properties_live` extension. It has no
in-memory or pure-Python fallback. Mutation commands require either the
complete native service or the exact-hash experimental live service, and each
selected target must be enabled in the service capability map. Unsupported
targets are reported before the tester performs any mutation.

The release build vendors the matching typed public Python API in the same
wheel so server plugins and the test harness cannot accidentally resolve a
differently versioned API installation.

The Linux wheel also carries the exact LLVM 18 `libc++.so.1`,
`libc++abi.so.1`, and `libunwind.so.1` runtime libraries used to build its
bridge. They are resolved only from the wheel's package-local `_native_libs`
directory, so no host package installation or `LD_LIBRARY_PATH` change is
required.

Install the native plugin and its matching tester wheel in the server's
`plugins/` directory. Tagged releases provide a compatibility-qualified ZIP
with both files already under `plugins/`; the plugin inside that bundle is
named `endstone_dynamic_properties_api.so`. Then use these commands as an
operator:

```text
/dptest status
/dptest run world confirm
/dptest run player confirm
/dptest run configured confirm
/dptest run all confirm
/dptest inventory all
/dptest watch start
# Make dynamic-property changes through Script API or another native caller.
/dptest watch drain
/dptest watch probe
/dptest watch status
/dptest watch stop
/dptest persistence prepare
# Restart the server cleanly.
/dptest persistence verify
/dptest report
/dptest cleanup confirm
/dptest help
```

On first enable the tester creates `targets.json` in its data folder. The file
contains disabled examples for all 12 target families. Replace the placeholder
identities and locations, enable only records prepared for a disposable test,
and use `run configured` to exercise create, read, successful edit,
stale-revision rejection, remove, clear, and flush on each target. `all`
combines the live world/player shortcuts with every enabled configured record
and rejects duplicate targets.

`inventory` is read-only. It enumerates and captures every collection visible
to the tester's own non-administrative namespace on the selected targets, so
old and current tester-owned values are retained in an integrity-sealed report.
It does not bypass normal plugin collection isolation. `watch` starts a bounded
native observer for before/after external-mutation events; `drain` atomically
removes the queued events into a report and records if the 1,024-event queue
overflowed. Watching proves interception only when the service reports an
active external-mutation hook capability. The alpha.5 exact-hash experimental
adapter enables that capability for world targets only; online-player and
loaded-entity targets are fail-closed while their actor boundary is reworked.
`watch probe` performs an operator-only, self-cleaning world probe through the
raw hooked Bedrock entry points and verifies
set/remove/clear before-and-after interception plus cancellation.

`persistence prepare` records a reload-stable, random server-process
incarnation token. `persistence verify` refuses to proceed until that token has
changed, so PID reuse cannot reject a real restart and a plugin reload cannot
accidentally satisfy the check.

`run` checks bool, finite double, UTF-8 string, and Vector3 round trips,
successful edits, optimistic revision conflicts, remove, collection clear,
and persistence flush. `player` derives the online player's XUID from the
authenticated command sender; neither a plugin ID nor administrative access
can be supplied on the command line. All tester mutations use only
`endstone-plugin:dynamic-properties-tester:acceptance`.

Reports are stored under the plugin data folder as `latest-report.json` and
`reports/<run-id>.json`. Active work is also atomically checkpointed in
`active-checkpoint.json`. A restart never replays an interrupted mutation.
Cleanup removes a value only if its target, fixed collection, key, and exact
runner-generated value still match the ownership record. Changed values are
preserved and reported as conflicts. Cleanup ownership is released only after
the corresponding remove or clear has been confirmed by readback and durably
flushed.
