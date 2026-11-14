# Probe runs on SolidWorks 2024

SolidWorks 2024 SP5 (revision 32.5.0), Student Edition, on the same machine as the
2026 runs one folder up. `../latest.json` stays the 2026 evidence that `findings.py`
and its tests are checked against; `latest.json` here is the last 2024 run.

The names of the user's own documents, open in the same session, are replaced
with `<user document N>`. The probe's own documents keep their names.

| Run | Result | What it shows |
|---|---|---|
| 20261102-193119 | 12 pass, 1 FAIL, 41 SKIP | `document_units` tried the 2026 folder's template, which 2024 cannot open. A probe bug, fixed: a template from a newer release is no longer tried. |
| 20261102-194425 | 50 pass, 1 HUNG, 3 NOT RUN | Everything but the end-to-end helical build passes, with the same decisions as 2026. `helical_end_to_end` took longer than the 120 s default timeout; on 2026 it also took 190 s. |
| 20261102-195904 | 40 pass, 2 FAIL, 2 SKIP | The helical and bevel builds each had one global refused by `Add2`. Not reproduced in a fresh session (20261103-130406); the session had made ~300 documents and grew to 22.8 GB, and the user was working in it. |
| 20261102-211723 | 36 pass, 1 HUNG, 7 NOT RUN | `assembly_distance_link` hung on a modal "Save Modified Documents" when the probe closed its scratch assembly. 2026 never asked. Fixed in the probe: `scaffold.save_created_parts` saves the probe's own parts first. The app never closes documents, so it is not affected. |
| 20261103-130406 | **44 pass** | In a freshly started SolidWorks: every end-to-end build (spur, helical, internal, bevel, crossed) passes through `swbuild.build`, with the same decisions as 2026. |
| 20261113-165651 | **24 pass** | The three probes written without SolidWorks, `bevel_planes_beyond_90`, `custom_properties` and `gear_mate` (with what they need), in the user's own session with one of their documents open. Every fact matches the 2026 run of the same day (`../probe-results-20261113-164531`): the same signs, enum values, read route and turns. Run in the user's session rather than a fresh one, because the probe attaches to the newest session and cannot be pointed at a second 2024. |
| 20261113-184353 | **32 pass** | Probe tier 7 (`p7_workbook`, PLAN-WORKBOOK §4.2) with its extras and what it needs, in the user's session: the workbook's layout part and static assembly. Every decision matches the 2026 full run (`../probe-results-20261113-183654`). The one difference is the template's: the first component of a new assembly came in fixed here, floating on 2026. Components came back fully resolved after a reopen. `tests/test_findings.py` pins tier 7 against this file and 2026's `latest.json` alike. The session grew from 6.9 to 10.3 GB. |
| 20261113-184630 | **16 pass** | `gear_mate` again, now fixing its first cylinder before unfixing it, so `UnfixComponent` is really exercised (here the cylinder came in fixed anyway). Same findings: numerator first, Flip False turns an external pair opposite ways. |
| `gear-pairs-20261113-184641.log` | spur, ring ok | `probe/gear_pairs_check.py`: a 20 / 40 spur pair and a 20-tooth pinion in a 60-tooth ring, built through `pair.assembly_plan` to turn, gear 1 driven 30°. Spur 1 : 2 opposite ways; ring and pinion 3 : 1 the same way with Flip False, no interference after the turn. With Flip True (what `pair.py` used to give a ring) the pinion turned against the ring and the teeth clashed (2026, `../gear-pairs-20261113-173157-ring-flip-true-before-the-fix.log`; fixed, `../gear-pairs-20261113-173930.log`). The crown and internal bevel pairs were not built here: the session was at 12 GB with 3.9 GB free. They built clean on 2026. |

| 20261113-223412 | **31 pass** | Probe tier 8 (`p8_motion`, PLAN-WORKBOOK §4.4, phase W5's motion) and what it needs, run from a `git archive` snapshot of b9ddb12 in the user's 2024 session freshly restarted (PID 52548, 0.7 GB, no document of theirs open; 5.7 GB at the end), after its 2026 run of the same code. Every tier 8 decision matches 2026's full run (`../latest.json`): a gear held by its Gear Axis coincident with the layout axis and its origin's distance from the layout's Front; a concentric mate between two axes refused; every gear mate turning the way its gears mesh with Flip False; a lock alone holding a compound pair; both 12 : 1 trains 1/12 the same way, one degree of freedom; the phase put right by a Transform2 put with the gear mate on. The one difference: GetErrorCode2 gave 51 for every flagged mate where 2026 gave 46, 47 and 1 (the same mates, the same warnings). `gear_mate_sense` took 682 s here against 492 s on 2026. |
| `w4-workbook-assembly-20261113-200555.log` | section a to the update; **stopped** at the 2 GB floor | `probe/workbook_assembly_check.py` (W4's demonstration, phase W4), section a, in the user's own session (PID 68820, not restarted since 15:56; 11.8 GB at the start), with one of their documents open. The 12 : 1 fixture built through the app's own code (4 parts, layout, assembly, 90 s), every frame at 0 mm / 0° off, every layout axis where its shaft is and along +Z, no interference, each mesh's half-pitch control clashing with its partner alone, reopened and found by name; the Excel edit (S2 X 64.5, G2 69 teeth) polled, classified, and carried by Update SolidWorks (29 s), saving nothing, measured again, and the 69-tooth G2 proven in the assembly (back at its old frame it runs into G1, 180.6 mm³). The session then reached 16.4 GB with 1.97 GB free, so the run stopped before the structural step and build-again `_r2`, closed its documents and quit its Excel. Section b (the pure move) was not started and section c (the risky placements) was not run here: section a took the session from 11.8 to 16.4 GB, and it settled at 13.0 GB with 3.3 GB free once the run's documents were closed, so another section would meet the 2 GB floor part-way while growing the user's session further; both wait for that session to be restarted. The 2026 runs, `../w4-workbook-assembly-20261113-194228.log` (all four sections, 244 checks) and `../w4-workbook-assembly-20261113-200255-a2.log`, are the whole demonstration. |

Where 2024 and 2026 differ (2026-11-13; the 2026 evidence is `../latest.json`):

- `first_component_fixed` is True on 2024 and False on 2026. Not a version
  difference but a template one: this machine's 2026 default assembly template
  is now `MMGS 8 Decimals.asmdot`, with which the first component comes in
  floating; the stock template fixed it on 2026 too (2026-09-15). The build fixes
  or unfixes each component itself, so it does not depend on either.
- `set_units_mmgs_after_new` no longer differs: both defaults are millimetres,
  so there is nothing to set. Setting an inch template to MMGS is pinned by the
  2026-09-15 run (`../probe-results-20260915-023929.json`) and has not been
  exercised on 2024.
- `shared_ends_are_one_point` is None in 20261103-130406 only because that probe
  was not among those run; it matched 2026 in 20261102-194425.

`latest.json` here is the last FULL 2024 run, 20261103-130406 (44 pass, every
end-to-end build). Shorter runs made since, in the user's own session, are kept
as their timestamped files and listed in the table, but do not replace it: a
partial run's decisions (`flank_recipe` STOP, `end_to_end` False) are what the
probes it left out would have said, not what 2024 does.

The end-to-end builds are memory-hungry on 2024: SolidWorks went from 0.3 GB to
12 GB during the helical build and gave most of it back afterwards. A session
that has made hundreds of documents does not give it all back.

`w2-build-20261113-165706.log` is phase W2's workbook build on 2024, in the same
session: `tests/fixtures/excel/Reducer_12to1.xlsx` read, planned and built by
`swbuild.build_many` through the app's own code, 4 gears to 4 parts; each part's
`.gear.json` variables equal those of a twin built from the same `GearSpec` the
strip's way; a second build refused before making anything. The 2026 run is
`../w2-build-20261113-164647.log`.
