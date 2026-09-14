#!/usr/bin/env bash
# Probe the SolidWorks API from WSL, through the Windows Python beside SolidWorks.
#
# The repo stays on ext4; Windows reads it through \\wsl.localhost. Every path
# handed to SolidWorks itself is under C:\, and the results come back through
# the same UNC path as plain file I/O. Carriage returns are stripped so the
# report reads cleanly here.
set -o pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python.exe "$(wslpath -w "$here/probe.py")" --out "$(wslpath -w "$here/probe/results")" "$@" | tr -d '\r'
exit "${PIPESTATUS[0]}"
