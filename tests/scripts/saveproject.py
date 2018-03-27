### Initialise a project with data and a framework file
from atomica.project import Project
from atomica.workbook_export import writeWorkbook
from atomica.system import SystemSettings as SS
from atomica.framework import ProjectFramework
from atomica.workbook_export import makeInstructions
from atomica.project_settings import ProjectSettings
from atomica.system_io import saveobj, loadobj
from atomica.utils import odict, tic, toc, blank

F = loadobj(os.path.join(tempdir,'testframework.frw'))
P = Project(framework=F) # Create a project with no data
databook_instructions, use_instructions = makeInstructions(framework=F, data=None, workbook_type=SS.STRUCTURE_KEY_DATA)
databook_instructions.num_items = odict([('prog', 3),       # Set the number of programs
                                         ('pop', 1), ])     # Set the number of populations
P.createDatabook(databook_path="./temp/databooks/databook_sir_blank.xlsx", instructions=databook_instructions, databook_type=SS.DATABOOK_DEFAULT_TYPE)

P = Project(framework=F, databook="databooks/databook_sir.xlsx")
# Note, P.runsim() currently returns interpolated parameters, not an actual model result. Model doesn't exist yet

# Save the framework object
P.save('./temp/testproject.prj')