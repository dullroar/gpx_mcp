#!/usr/bin/env python3
# Regenerate tests/schemas.json from the live server tool schemas.
#
# Run me when: I changed a tool signature on purpose and tests/test_tool_contract.py reports a schema diff.
"""Write the discovery snapshot. Review the diff before you commit it."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import conftest  # noqa: E402

tmp = Path(tempfile.mkdtemp())
tools, _ = conftest.Client(tmp, tmp).run([])
(ROOT / "tests" / "schemas.json").write_text(
    json.dumps({t.name: t.inputSchema for t in tools}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {len(tools)} tool schemas")
