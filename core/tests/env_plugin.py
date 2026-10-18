"""Pytest plugin loaded via `-p` (see pytest.ini) so it runs before Django settings load.

Gives tests the development defaults without needing a real secret key.
"""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
