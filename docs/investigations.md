# Cross-thread investigation register

Consolidated **2026-11-08**. This is an evidence index, not a wiring procedure
or approved shopping list. No vehicle or probe was accessed during this audit.
Dates below use the thread timestamps (UTC); the probe flashing took place on
November 7 in America/Denver, November 8 UTC.

## Coverage and repository state

| Workstream | Result retained | Repository disposition |
|---|---|---|
| Original teardown and measurements | Photos, CON1 tracing, chip identification, unplugged-panel observation | Already on `main` through `ef54200` |
| Debug header | Dan confirmed CON2 pin 1 as 5 V; pin 3 is ground; remaining signals tentative | Existing uncommitted README/electronics/findings edits retained in this PR |
| Probe flashing | F411 Black Pill flashed and verified; original probe backup saved | Recorded below; no panel firmware involved |
| Communication/lock check | Probe responds; two target scans failed; protection unknown | Electronics and findings updated |
| Firmware research | Related-family lead only; no demonstrated C21 bypass | Recorded as unresolved, not a working extraction method |
| Equipment discussions | Scope-first plan and candidate hardware; contradictory compatibility advice | Preserved as candidates requiring validation |

At audit time there were no GitHub PRs, and all five task worktrees were clean.
The flashing and vulnerability branches pointed to `14b3974`, an ancestor of
`main`; the other three pointed to `ef54200`. None had commits outside `main`.
Separate PRs for those branches would therefore be empty. One consolidated
documentation PR captures the remaining chat-only results and pending edits.
Existing task branches/worktrees are preserved, not deleted or rewritten.

## Probe artifacts

The flashing thread reported Black Magic Probe **v2.0.0**, built for
`blackpill-f411ce`, including its bootloader. The original **probe's** 512 KiB
flash was backed up before flashing. This is not a backup of the SAM C21 panel.

Artifacts remain outside Git at `/home/danb/.local/share/blackmagic-f411/`.
During consolidation, file sizes and SHA-256 hashes were checked, and `cmp`
confirmed the combined build and readback are identical:

| File | Bytes | SHA-256 |
|---|---:|---|
| `original-flash.bin` | 524288 | `d4b7ebf889c5d503ba162d1c25710d6beb6ecae85c702c13b727c2b82b329f0b` |
| `blackmagic-v2.0.0-f411ce-combined.bin` | 166752 | `03835baef268e58197544ba5361ea22d36af0fad3646fee62532ede8899fb615` |
| `flash-readback.bin` | 166752 | `03835baef268e58197544ba5361ea22d36af0fad3646fee62532ede8899fb615` |

The local files are not a portable archive or a complete reproducible build
record. Compiler settings and upstream source commit were not recovered into
this repository. Preserve these files separately before reusing the probe.

## Target communication result

On November 8 UTC, the probe responded on `labrador-pie` as Black Magic Probe
v2.0.0. Target scans at approximately **195 kHz** and **20 kHz** failed. Dan
reported the panel powered with a verified 5 V reference, using B8/B9, with
reset disconnected. The probe's voltage report was “Unknown,” not a measurement.
The test thread reported no target writes, erases, unlocks or reset commands.

**Failure to communicate does not establish a security lock.** CON2 signal
continuity, exact connection order, common ground, waveforms, input thresholds
and interface ratings remain checks, not proven causes. No DSU protection-bit
read or panel dump was obtained.

## Equipment advice requiring reconciliation

These are historical discussion candidates, not current purchasing advice.
No order or successful use of this equipment on the panel was recorded.

- The discussions conflict about genuine ST-LINK/V2 target-voltage support.
  Do not choose a probe from those statements; check the exact model's official
  interface specification. A 5 V power output is not proof of 5 V SWD support.
- Black Pill PB8/PB9 tolerance and PA5 reset protection were discussed from
  memory. Neither the blanket “fail, not fry” assurance nor a series resistor
  alone is accepted here as a validated interface design.
- TXS0108E, TXB0104 and earlier BSS138 boards were suggested, but no translator
  was validated for this target's bidirectional SWDIO, reset, loading or timing.
  Pi GPIO, Pico and Arduino proposals were not tested substitutes.
- CANable 2.0, NUCLEO-G431KB plus a transceiver, and Adafruit #5708 were
  candidates. Verify board revision, controller/transceiver capabilities,
  firmware and host support before purchasing. *(2026-11-09: a CANable 2.0 was
  used to capture the panel at 500 kbit/s classic CAN; see
  [can-bench-capture.md](can-bench-capture.md).)* No ready Nucleo build was
  demonstrated; estimates of porting effort were speculative.
- The cost-conscious sequence discussed was to use the existing Rigol scope
  first, then decide whether a long-duration CAN logger is needed. No scope
  capture or CAN log was saved. Probe positioners / magnetic PCB probe holders
  (including PCBite) were discussed; no particular kit was selected.
- PGM-09825 was rejected in its thread as an AVR ISP programmer rather than
  the required SWD probe. Other named probes remain model-specific candidates,
  not verified purchases for this setup.

## Next evidence gates

1. Document connector-face orientation and verify the remaining CON2 signal
   continuity before treating the candidate pin table as a cable pinout.
2. Validate electrical compatibility against exact probe and target specs;
   keep target-power outputs disconnected and avoid unvalidated reset wiring.
3. Resolve target communication before drawing conclusions about protection.
   Preserve original panel firmware; do not accept erase/unlock/recover prompts.
4. Record scope traces, bitrate and switch/LED tracing before choosing a CAN
   adapter or button-interface circuit. Start bus observation listen-only.
   *(2026-11-09: bitrate and Parking Safety switch traced; see the addendum.)*
5. Keep firmware research separate from demonstrated results. The SAM4C32
   discussion does not establish a SAM C21 bypass or a need for fault injection.

## Addendum: bench CAN session, 2026-11-09

Recorded after this audit. The panel was powered on the bench (12 V, 0.1 A
limit) and captured with a CANable 2.0 from `labrador-pie`; nothing was
transmitted. It sends `0x451` every 200 ms at 500 kbit/s without the car, and
byte 0 carries the two seat heater buttons. Parking Safety, steering wheel heat
and camera produced no CAN change. Dan then traced the Parking Safety switch to
CON1 pin 5 via ~200 Ω, other side to ground. Full results:
[can-bench-capture.md](can-bench-capture.md); raw logs:
`captures/2026-11-09-bench-can/`.

## Addendum: in-car CAN session, 2026-11-12

Listen-only at the panel connector, car on; nothing transmitted. The bus
carries ~195 IDs at 500 kbit/s. Another module reports Parking Safety in
`0x05C17002` (byte 1 `09` = auto-brake on, `07` = off; byte 0 bit 0 = warning
sound). Long presses toggle auto-brake both ways. Pin 5 reads 12.2 V released.
Details: [can-car-capture.md](can-car-capture.md); raw logs:
`captures/2026-11-12-car-can/`.

## Source threads

These T3 links preserve provenance for readers with access; the repository
summaries above stand alone for readers without access.

- [Original teardown and measurements](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/28b31148-01cd-4470-b3db-727dbcf18a3b>)
- [Debug-header confirmation](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/4dcca323-c3c1-4636-90f9-80d4808f9955>)
- [Probe flashing](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/20ea3afa-a351-467d-a7b1-888c3433c5b7>)
- [Communication and protection check](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/f56e3766-771e-47e0-b931-7bc444f8727b>)
- [Firmware research](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/c4477b63-db4f-46f6-b019-04f96917deaa>)
- [Programmer compatibility discussion](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/6eb107e4-b792-4c09-8416-3351d4361108>)
- [Equipment and probe holders](<t3-thread://v2/2fc5a6a7-9883-4475-a7f1-a31b60be5879/a27881c7-ec11-4d2c-8a25-411c51098c3b>)
