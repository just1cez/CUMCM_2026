import importlib.metadata
import json
import sys

print(
    json.dumps(
        {
            "python": sys.version,
            "executable": sys.executable,
            "packages": {
                name: importlib.metadata.version(name)
                for name in ("numpy", "scipy", "pymupdf")
            },
        },
        indent=2,
    )
)
