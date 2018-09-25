## This script tests some databook IO operations

import atomica.ui as au
from atomica.excel import transfer_comments
import numpy as np
from atomica.ui import ProjectFramework, Project, ProjectData
import sciris as sc

F = ProjectFramework("./frameworks/framework_tb.xlsx")
F.save('./temp/f_blug.xlsx')
#
# Copy a databook by loading and saving it
data = ProjectData.from_spreadsheet("./databooks/databook_tb.xlsx",F)
data.save('./temp/d_blug.xlsx')

# Copy comments, using lower-level AtomicaSpreadsheet (for in-memory file operations)
original_workbook = au.AtomicaSpreadsheet("./databooks/databook_tb.xlsx")
new_workbook = data.to_spreadsheet() # This is a AtomicaSpreadsheet that can be stored in the FE database
transfer_comments(new_workbook,original_workbook)
new_workbook.save('./temp/d_blug_formatted.xlsx')

# Run the copied databook
P = Project(name="test", framework=F, do_run=False)
P.load_databook(databook_path="./temp/d_blug.xlsx", make_default_parset=True, do_run=True)
d = au.PlotData(P.results["parset_default"], pops='0-4')
au.plot_series(d, plot_type="stacked") # This should look like the usual Optima-TB result

# Change the time axis
d2 = sc.dcp(data)
d2.change_tvec(np.arange(2000,2017,0.5))
d2.save('./temp/d_blug_halfyear.xlsx')

# Run the half-year databook
P = Project(name="test", framework=F, do_run=False)
P.load_databook(databook_path="./temp/d_blug_halfyear.xlsx", make_default_parset=True, do_run=True)
d = au.PlotData(P.results["parset_default"], pops='0-4')
au.plot_series(d, plot_type="stacked") # This should look like the usual Optima-TB result

# Change the pops and run it
data = ProjectData.from_spreadsheet("./databooks/databook_tb.xlsx",F)
data.rename_pop('0-4','0-3','Gen 0-3')
data.rename_transfer('age','age_up','Age Up')
data.save('./temp/d_blug_renamed.xlsx')
P = Project(name="test", framework=F, do_run=False)
P.load_databook(databook_path="./temp/d_blug_renamed.xlsx", make_default_parset=True, do_run=True)
d = au.PlotData(P.results["parset_default"], pops='0-3')
au.plot_series(d, plot_type="stacked") # This should look like the usual Optima-TB result

# Remove a key pop
d2 = sc.dcp(data)
d2.remove_pop('Prisoners')
d2.save('./temp/d_blug_nopris.xlsx')

# Remove a transfer, add an interaction, add a pop
d2.remove_transfer('inc')
d2.add_interaction('d_ctc','New interpop')
d2.add_pop('asdf','The ASDF pop')
d2.save('./temp/d_blug_newpop.xlsx')

# Make a brand new databook
d2 = ProjectData.new(F,np.arange(2000,2017),pops=2,transfers=4)
d2.save('./temp/d_blug_blank.xlsx')

# Make a blank databook with the same pops and transfers from the old one
pops = sc.odict()
for pop,val in data.pops.items():
    pops[pop] = val['label']

transfers = sc.odict()
for transfer in data.transfers:
    transfers[transfer.code_name] = transfer.full_name

d2 = ProjectData.new(F,np.arange(2000,2017),pops=pops,transfers=transfers)
d2.save('./temp/d_cleared.xlsx')

# Modify incomplete databook
d2 = ProjectData.from_spreadsheet('./temp/d_blug_blank.xlsx',F)
d2.add_pop('asdf','The ASDF pop')
d2.add_interaction('d_ctc','New interpop')
d2.save('./temp/d_blug_blank_modified.xlsx')