# Jidan capability kernel — executable sketch

This dependency-free Python prototype tests one architectural claim: an AI planner must not be the security boundary. A model may propose a task graph, but a deterministic kernel must validate capabilities and their schemas, attenuate authority, stop for consent, execute adapters, and produce hash-chained receipts.

## Core demo

The original demo searches local mail, extracts recipe ingredients, and requests a shopping-list write. It stops before any step executes until that write is approved, then emits one hash-chained receipt per step.

Run from this directory with Python 3.11+:

```powershell
python demo.py
python demo.py --approve
python -m unittest discover -s tests -v
```

## Android 17 AppFunctions Phase 1 adapter

`jidan/android_appfunctions.py` is an argv-only adapter for the official Android shell surface:

- device probe: `adb get-state`, then `adb shell cmd app_function help`;
- discovery: `adb shell cmd app_function list-app-functions [--package ...]`;
- execution: `adb shell cmd app_function execute-app-function --timeout-duration 30 --package ... --function ... --parameters ...`;
- normalization into conservative Jidan capabilities and dynamic `CapabilityRegistry` binding;
- exact raw list/execute responses through `list_raw()` and `execute_with_raw()`;
- typed failures for `adb_missing`, `device_offline`, `permission_denied`, `unsupported`, `parse_failure`, and generic command failure.

The Android 17 platform image has two observed compatibility details covered by regression tests: `cmd app_function help` can emit its valid help page on stderr with exit code 255, and platform providers can use simple opaque IDs such as `getPermissionsDeviceState` in addition to AndroidX-style `Class#method` IDs.

Every subprocess receives an argv list with `shell=False`. Dynamic device-shell values are individually POSIX-quoted because `adb shell` joins its tail into a command interpreted on the device. JSON is generated with the standard library, rejects non-finite values and mixed-type arrays, and rejects null/empty-array fields that Android's GenericDocument converter cannot represent. It never silently changes already approved parameters or interpolates user data into a command string.

The prototype caps encoded parameters at 16 KiB and the final quoted device command at 24 KiB, so the documented path stays below the practical Windows process-command boundary. It compiles supported Android primitive, array, and object parameter metadata into the dependency-free JCC schema subset, enforces it during preflight, and refuses to register input contracts it cannot compile safely. When response metadata is compilable it also validates the Android 17 `androidAppfunctionsReturnValue` shell envelope. A post-invocation output mismatch is recorded as `committed_unverified` and the task becomes `unknown`, never an ordinary retryable failure.

Run the complete no-device smoke—fake ADB discovery, dynamic capability registration, JGraph confirmation stop, approved execution, and receipt verification—with one command:

```powershell
python appfunctions_smoke.py
```

For a real Android 17 device, first probe the official ADB binary. The repository-local binary downloaded for this workspace can be checked with:

```powershell
python -m jidan.android_appfunctions --adb-path ..\..\..\work\android-platform-tools\platform-tools\adb.exe probe
```

With no connected device this intentionally returns a structured `device_offline` error. With an online device:

```powershell
python -m jidan.android_appfunctions --adb-path C:\path\to\adb.exe list --package com.example.notes
python -m jidan.android_appfunctions --adb-path C:\path\to\adb.exe execute com.example.notes 'com.example.notes.NoteFunctions#createNote' '{"title":"Jidan roadmap"}'
```

To run the discovered function through the full JGraph confirmation/grant/receipt path, use an exact device serial, absolute reviewed ADB path, controlled package, and disposable parameters. Omit `--approve` for a zero-side-effect preflight; add it only after reviewing the exact command. `${RUN}` and `${RUN_ID}` can make 30 test records unique:

```powershell
python appfunctions_live.py --adb-path C:\path\to\adb.exe --serial SERIAL --package com.example.notes --function 'com.example.notes.NoteFunctions#createNote' --parameters '{"title":"Jidan ${RUN_ID}"}' --runs 30 --receipt-log .\jidan-live-receipts.jsonl --grant-ledger .\jidan-live-grants.sqlite3 --initialize-grant-ledger
```

`--initialize-grant-ledger` is a one-time explicit provisioning action. After reviewing the preflight, rerun with the same `--grant-ledger`, omit `--initialize-grant-ledger`, and add `--approve`. A missing established ledger fails closed and is never silently recreated. Receipt and ledger paths must be distinct from the SQLite main file and its `-wal`, `-shm`, and `-journal` sidecars.

The harness is fail-fast and never automatically retries an ambiguous external action.

Programmatic JGraph binding is similarly small:

```python
from jidan import CapabilityRegistry
from jidan.android_appfunctions import AdbAppFunctionsAdapter

adapter = AdbAppFunctionsAdapter(adb_path=r"C:\path\to\adb.exe")
registry = CapabilityRegistry()
records = adapter.register_discovered(registry, package_name="com.example.notes")
```

Dynamic registration requires an explicit package filter, and every supplied discovery record is checked against that package. Discovered AppFunctions default to `external`, non-reversible, confirmation-required capabilities. Android metadata does not prove effect, reversibility, or compensation, so a trusted policy must explicitly refine those defaults.

This is a developer/extreme-user shell route, not a claim that an ordinary APK owns cross-app privileges. It does not integrate Shizuku or any community fork, does not use a pending-intent execution path, and does not provide a GUI/Accessibility fallback. The command contract follows the official [AppFunctions ADB testing reference](https://developer.android.com/agents/skills/device-ai/appfunctions/references/adb-interaction-testing).

## Semantic-surface routing

`jidan/semantic_surfaces.py` inventories app-authored Android surfaces before any
GUI controller is considered. The current priority is:

1. typed AppFunctions;
2. an active notification with `RemoteInput`;
3. a person-bound conversation shortcut;
4. a public text-share handoff that leaves recipient choice and send confirmation
   inside the target app;
5. fail closed with `blocked_no_semantic_surface`.

OCR, screenshots, and coordinates are deliberately absent from this routing
decision. They may later propose a visual candidate, but pixels cannot establish
the identity or authority required for an external send.

Run the read-only inventory through the normal Jidan grant, ledger, and receipt
pipeline:

```powershell
python semantic_surface_live.py --adb-path C:\path\to\adb.exe --serial emulator-5554 --package com.example.app --receipt-log .\surface-receipts.jsonl --grant-ledger .\surface-grants.sqlite3 --initialize-grant-ledger --summary .\surface-summary.json
```

The probe executes only package discovery, AppFunctions listing, shortcut
listing, notification inspection, and public `ACTION_SEND` handler discovery.
It never opens the target app, taps the screen, enters text, or sends a message.

## WeChat text-share handoff

`jidan/android_share.py` is a deliberately narrow bridge to WeChat's exported
Android text-share surface. It validates the installed handler, passes text via
`ACTION_SEND`, and opens WeChat's own recipient picker. It does not inspect
pixels, name a contact, select a row, press Send, or claim that a message was
sent. Contact identity stays inside WeChat.

Run the handoff through the Jidan capability, task-plan, grant, durable ledger,
and receipt pipeline:

```powershell
python wechat_share_live.py --adb-path C:\path\to\adb.exe --serial emulator-5554 --text-utf8-base64 5L2g5aW9 --receipt-log .\wechat-share-receipts.jsonl --grant-ledger .\wechat-share-grants.sqlite3 --initialize-grant-ledger --summary .\wechat-share-summary.json
```

The example payload is UTF-8 `你好`. Add `--approve` only after reviewing the
handoff. A successful approved run leaves WeChat at its exact recipient picker
with `jidanIssuedSend=false`; the user still chooses the contact and confirms
the final send.

## Language-neutral memo input

`parse_memo_command()` accepts `memo: <content>` in any Unicode writing system and maps it to the stable `memo.create` semantic action. A BCP 47 `locale_hint` can select a trusted natural-language adapter; the bundled Chinese rules remain the only free-form offline grammar in this prototype. Unknown locales fail closed unless the explicit `memo:` prefix is used.

This boundary is intentional: language adapters may interpret text, but they cannot grant capabilities or execute task-graph nodes.

## Windows Unicode arguments

Windows PowerShell 5.1 can replace Unicode with `?` before Python when text is sent through its native pipeline. Pass natural-language values as normal argv instead. `alarm_live.py` also accepts `--message-utf8-base64`, an ASCII-only transport that is safe across that boundary. It decodes back to UTF-8 before Jidan builds the task plan.

If a native PowerShell pipeline is unavoidable, both ends must be configured:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
```

## Controlled Reference App acceptance

`reference_app_validation.py` is the final real-device harness for `../reference-app`. It requires a new `--grant-ledger` path and provisions that SQLite ledger explicitly. For each of 30 rounds it proves a zero-execution unapproved preflight, one approved physical write plus exact readback, rejection of the consumed Jidan grant, and an independently approved provider-level idempotent replay. After round 1 it releases the old Runtime, PolicyEngine, and ledger objects, reopens the database, and proves the already-consumed grant remains rejected with zero provider delta. It then force-stops and restarts the provider process, replays round 1 after all 30 writes, verifies the immutable operation snapshot versus the current round-30 memo, and attempts one conflicting reuse of the final operation ID.

Successful Runtime steps are written to the normal receipt chain. Negative preflight/replay/collision assertions and the process restart are written to a separate hash-chained test-event log, including provider counters before or after the event. The final accepted run produced 122 successful receipts, 63 test events, 30 physical mutations, and 62 total provider invocations (30 writes + 30 immediate replays + 1 delayed replay + 1 rejected collision).

## Prototype trust boundary

Use only controlled reference apps and disposable, idempotent test data on a real device. Demo runtimes still default to `InMemoryGrantLedger`; real-device entry points explicitly require `SqliteGrantLedger`. The durable ledger provides cross-process, local-disk at-most-once authorization while the same database continuously exists. A crash after ledger COMMIT but before provider dispatch permanently consumes the grant and may produce zero task executions; this is fail-closed, not exactly-once recovery. SQLite `quick_check` does not detect legitimate row deletion or rollback to an older valid database. Receipt/event hashes likewise are not authenticated against an attacker who can rewrite the entire chain, and `ReceiptLog` is not a cross-process atomic appender. The system version needs protected file ownership plus an Android Keystore/StrongBox HMAC or signature anchor and a durable task state machine. Discovered package metadata is untrusted and remains `external`, non-reversible, and confirmation-required; the true-device harness adds a package-signing-certificate allowlist before enabling writes.
