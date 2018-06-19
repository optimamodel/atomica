# -*- coding: utf-8 -*-
"""
Atomica module initialization file.

License:

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU Lesser General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Display version information using logging
import logging
logger = logging.getLogger() # Get the root logger, keep its level
h = logging.StreamHandler()
h.setFormatter(logging.Formatter(fmt='%(asctime)-20s %(levelname)-8s %(message)s',datefmt='%d-%m-%y %H:%M:%S'))
logger.addHandler(h)
del h

import atomica.core.version
logger.critical( 'Atomica %s (%s) -- (c) the Atomica development team' % (atomica.core.version.version, atomica.core.version.versiondate)) # Log with the highest level
try:
    import sciris.core as sc
    atomica_git = sc.gitinfo(__file__)
    logger.critical('git branch: %s (%s)' % (atomica_git['branch'],atomica_git['hash']))
    del atomica_git
except:
    pass

# Import things for the user
from . import core # All Atomica functions
from . import ui as au # The actual Atomica user interface

# Import app flavors
try:
    # from . import apps
    pass
except Exception as E:
    import traceback
    app_error = traceback.format_exc()
    logger.error('Could not load apps - see atomica.app_error for details')

# Finally, set default output level to INFO
logger.setLevel('INFO')
