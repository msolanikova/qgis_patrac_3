# Run inside QGIS: Plugins > Python Console > Show Editor > open this file > Run.
# QGIS was started with tools/dev/run_qgis.sh, so QGIS_PY is set in its environment.
import os

import debugpy

debugpy.configure(python=os.environ["QGIS_PY"])  # sys.executable is the QGIS binary, not Python
debugpy.listen(("127.0.0.1", 5678))
print("debugpy listening on 127.0.0.1:5678 - attach from the IDE")
