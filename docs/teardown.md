# Teardown: console switch panel

Vehicle: 2025 Ioniq 5 XRT (facelift console). Dan confirmed this removal
method worked on his car on **2026-11-07**. Disconnect the 12 V negative
before unplugging connectors; reconnect only after the panel is secured and
loose tools/probes cannot short anything.

## 1. Remove the glossy upper console panel

Credit: the method comes from an r/Ioniq5 owner's
[MagSafe charger install post](https://www.reddit.com/r/Ioniq5/comments/1t76ayr/built_in_magsafe_phone_charger_without_exposed/),
which has photos of the screws and pry points. It works on the XRT.

1. Pull the rubber mats out of both cupholders.
2. Remove the two screws, one under each mat.
3. Slide a wide plastic trim tool under the front-centre edge of the glossy
   panel and pry up to release the clips (roughly 6-8).
4. Work around the edges and lift the panel without stretching the wiring.

## 2. Unplug the button assembly

Press the latch and pull the harness plug off the switch assembly. It is a
16-position KET plug (2 rows of 8, 14 wires populated) with a yellow
terminal-position lock.

| | |
|---|---|
| ![In car](../photos/teardown/01-connector-in-car.png) | ![Unplugged](../photos/teardown/02-harness-plug-unplugged.jpg) |
| Connector in place | Harness plug unplugged |
| ![KET marking](../photos/teardown/03-harness-plug-ket-marking.jpg) | ![Header](../photos/teardown/04-switch-header-16pin.jpg) |
| KET moulding, yellow lock | 16-pin header on the switch |

## 3. Remove the button assembly and open it

The assembly is held into the panel by four plastic clips around its edge.
Release them and pull it out. The PCB, rubber button membrane and a plastic
carrier then come out of the housing together.

| | |
|---|---|
| ![Back](../photos/teardown/05-button-assembly-back-clips.jpg) | ![Side](../photos/teardown/06-button-assembly-side-clips.jpg) |
| Assembly back | Edge clips |

Board details are in [electronics.md](electronics.md).

## 4. Keep the measurements tied to the right connector

`CON1` is the 16-position vehicle connector; `CON2` is the separate five-hole
header on the PCB. Mark orientation before bench work: “top” in a photograph
is not a connector numbering standard. The current pin assignments and
unverified details are in [findings.md](findings.md#con1-16-position-vehicle-connector).

Keep the rubber membrane and carrier aligned when reassembling, seat the
four clips, reconnect the harness latch, and refit the upper panel, screws
and mats. Check the manual buttons/indicators after reassembly; no completed
reassembly/function checklist was reported in the chat.

Dan reports the car works fine with this module unplugged. That observation
is recorded separately in [findings.md](findings.md#car-behaviour-with-the-panel-unplugged);
it is not confirmation that rear auto-braking is off or all functions remain
available.
