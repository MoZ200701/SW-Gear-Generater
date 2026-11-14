# W4: the orchestrator's decisions on the plan and its review

Read in this order: `docs/PLAN-WORKBOOK.md` (the authority), `W4-PLAN.md` (the implementation plan),
`W4-PLAN-REVIEW.md` (the independent review of that plan), then this file. Where they disagree, this file wins
over the review, the review over W4-PLAN, and PLAN-WORKBOOK over all three unless this file says a reading was chosen.

## Review findings: all accepted, with these rulings

1. **Helical placement across Z+/Z− (review 1).** Fixed first, on its own, in `workbook/geometry.py`
   (`Placed.twist` counts from the Profile Plane: `z_local + overrun` for a plain helical gear or ring),
   `helical.face_rotations` and the tests, which must model the part from the build code (`crossed.twist_at`),
   not from `space_angle`. W4's frame formula then stands as W4-PLAN §1.3 wrote it:
   `R = F_σ · rot_z(deg θ)`, `at = (x, y, z_front)`, `F₋ = rot_x(180°)`. A separate agent does this; W4 code
   builds on its commit.
2. **Parts across revisions (review 2).** The record's parts carry the revision that made them; Update and reuse
   act only on the parts the current revision's `gearbox.components[].part` names. Superseded parts stay listed
   under `earlier`, paths only.
3. **Reuse is verified live (review 3).** `build_gearbox` opens every reused part (and a reused layout) BEFORE it
   builds anything and requires `planned_changes(sw.equations(), variables, trig) == []`; otherwise `BuildError`
   naming the part and what differs, with nothing made.
   **Update SolidWorks does not save** (as the strip's Update values does not). The record marks an update as
   `unsaved` until the app sees it on disk; the footer says "Save in SolidWorks to keep it." Because reuse and
   Update both compare against live SolidWorks, a lost or unsaved update is put right on the next press.
4. **The layout part can be reused (review 4).** `GearboxPlan.layout` is either a plan to build or a path to
   reuse; `gearbox.layout`/`shafts` are written to the record as soon as the layout saves, even if the assembly
   then fails; a reused layout is opened and checked live (its globals and axes) before it is inserted.
5. **Misclassified edits (review 5).** Compare plans and stems first; normalise fields a kind ignores before
   `structural_change`. A spur gear's Hand, and a Part name equal to the default stem, are not structural.
6. **No dead ends (review 6, 7).** `plan_gearbox` always takes the smallest free revision. Files on disk with no
   record, a component renamed or deleted in SolidWorks, and our own stale parts all lead to an offered
   build-again, with a true sentence.
7. **Same-named documents (review 8).** Before a build or update, compare `documents()` against every path to be
   built, opened or inserted; a document of the same file name open from another folder is refused with a
   sentence naming both paths. After `AddComponent5`, check the component's path.
8. **The build-again question (review 9)** must not promise the old assembly is untouched: reused parts are shared,
   so a later Update changes the earlier revision's assembly too. Say so in the question.
9. **Build parts fallback (review 10)** goes through the same reuse as Build, so it can resume a partial batch.
10. **Windows demonstration (review 11).** Three workbooks, each on SolidWorks 2026 and 2024, logs committed:
    (a) the 12 : 1 fixture: build, measure, the Excel edit S2 X 63.75 → 64.5 with G2 Teeth 68 → 69 (S3 X follows
    by its formula), Update SolidWorks, measure, then the structural step and `_r2` with sha256 + mtime of every
    earlier file unchanged (required, not optional);
    (b) a pure move: a workbook with S2 off the X axis so a move alone keeps every mesh (both planes non-zero),
    S2 moved along its arc in Excel, Update moves it;
    (c) the risky placements: a helical pair across Z+/Z−, herringbones of unequal face widths, a ring on a Z−
    shaft. Every mesh gets the half-pitch negative control (turn one gear half a pitch: interference must
    appear; put it back: none). After the update in (a), a control proving the assembly shows G2's 69 teeth.
11. **Interfaces first (review 12).** One interface commit pins every shared dataclass and signature before the
    work is split. Planning never moves files (review 13). A gear's turn is compared modulo its pitch (review 14).

## Readings of PLAN-WORKBOOK chosen (a later review may overrule; do not re-open while implementing)

- Globals only for non-zero coordinates; a coordinate changing side or leaving/reaching 0 is structural.
- A Z± change, a Z change and an `At` change are moves while the assembly is static.
- Components are not renamed; the record maps gear → the Name2 SolidWorks kept.
- `<Name>_r<n>_Layout.SLDPRT` beside `<Name>_r<n>.SLDASM`.
- One build button whose label follows the gate (Build / Build parts / Build again…); Update SolidWorks beside it.
- A part keeps its file name after a value update (N68 holding 69 teeth); the sentence says so.
- A Part name change is structural only when the resulting stem changes.

## Rules for every agent on W4

- Commits: explicit paths only (`git add <paths>`; `git commit -m "…" -- <paths>`), prose messages with the why,
  **no Claude co-author or attribution line**, no push. Never `add -A`, `commit -a`, stash or reset.
- Read findings from committed `findings.py` only; never guess a SolidWorks call; every raise a full sentence.
- The repo is public: no user document titles in committed logs (`<user document N>`).
- SolidWorks 2024 on the host is the user's live session: close only what you created, never exit it.
