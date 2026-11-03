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

Two decisions read differently, and neither changes the build:

- `set_units_mmgs_after_new` is False because this machine's 2024 default template
  is already millimetres, so there was nothing to set. The build skips setting
  units when a part is already in millimetres. Setting an inch template to MMGS
  has not been exercised on 2024.
- `shared_ends_are_one_point` is None in 20261103-130406 only because that probe
  was not among those run; it matched 2026 in 20261102-194425.

The end-to-end builds are memory-hungry on 2024: SolidWorks went from 0.3 GB to
12 GB during the helical build and gave most of it back afterwards. A session
that has made hundreds of documents does not give it all back.
