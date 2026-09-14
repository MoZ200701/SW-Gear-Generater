"""What the probe settled about the SolidWorks API, as constants the tool reads.

Every value here is a finding, not a preference: each names the probe result it
came from and the version it was observed on. ``tests/test_findings.py`` checks
them against ``probe/results/latest.json`` through :mod:`probe.decide`, so they
cannot drift from the evidence. They are constants rather than runtime JSON
because the exe must behave the same for someone who never ran the probe.

PENDING: the probe (Phase 2) has not run yet. Until it does, the values below
are the plan's working assumptions and nothing in the build may rely on them.
"""

from __future__ import annotations

# Which tooth-flank recipe a new gear gets. "A" is the true involute through an
# Equation Driven Curve; "B" is circles, arcs and relations only.
DEFAULT_RECIPE = "A"  # PENDING probe tier 1

# The Equation Manager's trig units in a document made from the default
# template. The build measures every document anyway; this is only what the
# dry run prints.
TRIG_DEFAULT = "degrees"  # PENDING probe tier 1
