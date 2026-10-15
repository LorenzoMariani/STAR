"""Copy the selector GUI into the STAR FrontEnd so the END-019 results tab uses the same file.

    python tools/sync_gui_to_star.py ["path/to/Orchestrator and gui"]

The GUI is written once (gui/component_selector.html); STAR embeds it in web/modules/end019_results.html
(star_frontend_v2.py inlines it as an iframe srcdoc when it builds the results workspace)."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "Orchestrator and gui"
dest = target / "FrontEnd" / "web" / "modules" / "end019_results.html"
if not dest.parent.is_dir():
    sys.exit(f"STAR FrontEnd not found: {dest.parent}")
shutil.copyfile(ROOT / "gui" / "component_selector.html", dest)
print(f"copied to {dest}")
