# Load a framework object
from atomica.project import Project
from atomica.workbook_export import writeWorkbook
from atomica.system import SystemSettings as SS
from atomica.framework import ProjectFramework
from atomica.workbook_export import makeInstructions
from atomica.project_settings import ProjectSettings
from atomica.system_io import saveobj, loadobj
from atomica.utils import odict, tic, toc, blank

F = loadobj(os.path.join(tempdir,'testframework.frw'))