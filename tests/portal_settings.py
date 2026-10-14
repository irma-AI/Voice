import os

# The Portal's settings refuse to load without production values unless DEBUG is on; tests are a local run.
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("DEBUG", "1")

from portal.settings import *  # pyright: ignore[reportWildcardImportFromLibrary]
