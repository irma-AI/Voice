import os

# The Portal's settings refuse to load without production values unless DEBUG is on; tests are a local run.
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("DEBUG", "1")

from portal.settings import *  # pyright: ignore[reportWildcardImportFromLibrary]

# pytest-django turns DEBUG off, which would make WhiteNoise look for the collected files; tests serve the source ones, as a local run does.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
