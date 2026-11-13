#!/usr/bin/env bash
# The workbook's Windows checks against real Excel (PLAN-WORKBOOK W1–W3), from WSL, through the Windows
# Python beside Excel — as probe.sh does for SolidWorks. Opens and quits Excel instances of its own and
# the app's Workbook window; leave the machine alone while it runs (about five minutes).
#
#   probe/excel/run_all.sh <scratch folder, a Windows path under C:\>
#
# The app is checked as committed: HEAD's src/ is exported into the scratch folder and imported from
# there (GG_SRC), so edits in the working tree do not leak into the run. make_fixture.py is not run here:
# it remakes the committed fixture, a manual step.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
scratch="${1:?give a scratch folder, e.g. C:\\Users\\<you>\\Documents\\GearGeneratorProbe\\excel-checks}"
mkdir -p "$(wslpath -u "$scratch")/src"
git -C "$repo" archive HEAD src | tar -x -C "$(wslpath -u "$scratch")"
export GG_EXCEL_SCRATCH="$scratch" GG_SRC="$scratch\\src"
export WSLENV="${WSLENV:+$WSLENV:}GG_EXCEL_SCRATCH:GG_SRC"
echo "scratch: $scratch"
echo "app: $(git -C "$repo" log -1 --format='%h %s')"
cd /mnt/c    # python.exe starts cleanly from a Windows folder
for script in export_checks.py user_open.py locked_checks.py tk_driver.py; do
    echo "== $script"
    python.exe "$(wslpath -w "$here/$script")" | tr -d '\r'
done
