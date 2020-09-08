"""
Atomica version file.

Standard location for module version number and date.
"""

from .utils import fast_gitinfo
version = "1.21.3"
versiondate = "2020-09-08"
gitinfo = fast_gitinfo(__file__)
