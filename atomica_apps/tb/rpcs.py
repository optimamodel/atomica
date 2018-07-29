"""
rpcs.py -- code related to HealthPrior project management
    
Last update: 2018jun04 by cliffk
"""

#
# Imports
#

import time

def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        if 'log_time' in kw:
            name = kw.get('log_name', method.__name__.upper())
            kw['log_time'][name] = int((te - ts) * 1000)
        else:
            print '%r  %2.2f ms' % \
                  (method.__name__, (te - ts) * 1000)
        return result

    return timed


import os
from zipfile import ZipFile
from flask_login import current_user
import mpld3

import sciris.corelib.fileio as fileio
import sciris.weblib.user as user
import sciris.core as sc
import sciris.web as sw
import sciris.weblib.datastore as ds

import atomica.ui as au
from . import projects as prj

# Make a Result storable by Sciris
class ResultSO(sw.ScirisObject):

    def __init__(self,result):
        super(ResultSO, self).__init__(result.uid)
        self.result = result

# A ResultPlaceholder can be stored in proj.results instead of a Result
class ResultPlaceholder(au.NamedItem):

    def __init__(self,result):
        au.NamedItem.__init__(self,result.name)
        self.uid = result.uid

    def get(self):
        result_so = ds.data_store.retrieve(self.uid)
        return result_so.result

@timeit
def store_result_separately(proj,result):
    # Given a result, add a ResultPlaceholder to the project
    # Save both the updated project and the result to the datastore
    ts = time.time()
    result_so = ResultSO(result)
    result_so.add_to_data_store()
    proj.results.append(ResultPlaceholder(result))
    save_project(proj)

# Dictionary to hold all of the registered RPCs in this module.
RPC_dict = {}

# RPC registration decorator factory created using call to make_register_RPC().
register_RPC = sw.make_register_RPC(RPC_dict)

        
#
# Other functions (mostly helpers for the RPCs)
#
    

def load_project_record(project_id, raise_exception=True):
    """
    Return the project DataStore reocord, given a project UID.
    """ 
    
    # Load the matching prj.ProjectSO object from the database.
    project_record = prj.proj_collection.get_object_by_uid(project_id)

    # If we have no match, we may want to throw an exception.
    if project_record is None:
        if raise_exception:
            raise Exception('ProjectDoesNotExist(id=%s)' % project_id)
            
    # Return the Project object for the match (None if none found).
    return project_record

@timeit
def load_project(project_id, raise_exception=True):
    """
    Return the Nutrition Project object, given a project UID, or None if no 
    ID match is found.
    """ 
    
    # Load the project record matching the ID passed in.

    ts = time.time()


    project_record = load_project_record(project_id,
        raise_exception=raise_exception)

    print 'Loaded project record from Redis - elapsed time %.2f' % ((time.time()-ts)*1000)

    # If there is no match, raise an exception or return None.
    if project_record is None:
        if raise_exception:
            raise Exception('ProjectDoesNotExist(id=%s)' % project_id)
        else:
            return None
        
    # Return the found project.
    proj = project_record.proj

    print 'Unpickled project - elapsed time %.2f' % ((time.time()-ts)*1000)

    return proj

@timeit
def load_project_summary_from_project_record(project_record):
    """
    Return the project summary, given the DataStore record.
    """ 
    
    # Return the built project summary.
    return project_record.get_user_front_end_repr()

@timeit
def load_current_user_project_summaries2():
    """
    Return project summaries for all projects the user has to the client.
    """ 
    
    # Get the prj.ProjectSO entries matching the user UID.
    project_entries = prj.proj_collection.get_project_entries_by_user(current_user.get_id())
    
    # Grab a list of project summaries from the list of prj.ProjectSO objects we 
    # just got.
    return {'projects': map(load_project_summary_from_project_record, 
        project_entries)}

@timeit
def get_unique_name(name, other_names=None):
    """
    Given a name and a list of other names, find a replacement to the name 
    that doesn't conflict with the other names, and pass it back.
    """
    
    # If no list of other_names is passed in, load up a list with all of the 
    # names from the project summaries.
    if other_names is None:
        other_names = [p['project']['name'] for p in load_current_user_project_summaries2()['projects']]
      
    # Start with the passed in name.
    i = 0
    unique_name = name
    
    # Try adding an index (i) to the name until we find one that no longer 
    # matches one of the other names in the list.
    while unique_name in other_names:
        i += 1
        unique_name = "%s (%d)" % (name, i)
        
    # Return the found name.
    return unique_name

@timeit
def save_project(proj):
    """
    Given a Project object, wrap it in a new prj.ProjectSO object and put this 
    in the project collection (either adding a new object, or updating an 
    existing one)  skip_result lets you null out saved results in the Project.
    """ 
    
    # Load the project record matching the UID of the project passed in.

    ts = time.time()

    project_record = load_project_record(proj.uid)

    print 'Loaded project record - elapsed time %.2f' % ((time.time()-ts)*1000)

    # Create the new project entry and enter it into the ProjectCollection.
    # Note: We don't need to pass in project.uid as a 3rd argument because 
    # the constructor will automatically use the Project's UID.
    projSO = prj.ProjectSO(proj, project_record.owner_uid)

    print 'ProjectSO constructor - elapsed time %.2f' % ((time.time()-ts)*1000)

    prj.proj_collection.update_object(projSO)
    
    print 'Collection update object - elapsed time %.2f' % ((time.time()-ts)*1000)

@timeit
def save_project_as_new(proj, user_id):
    """
    Given a Project object and a user UID, wrap the Project in a new prj.ProjectSO 
    object and put this in the project collection, after getting a fresh UID
    for this Project.  Then do the actual save.
    """ 
    
    # Set a new project UID, so we aren't replicating the UID passed in.
    proj.uid = sc.uuid()
    
    # Create the new project entry and enter it into the ProjectCollection.
    projSO = prj.ProjectSO(proj, user_id)
    prj.proj_collection.add_object(projSO)  

    # Display the call information.
    # TODO: have this so that it doesn't show when logging is turned off
    print(">> save_project_as_new '%s'" % proj.name)

    # Save the changed Project object to the DataStore.
    save_project(proj)
    
    return None

@timeit
def get_burden_set_fe_repr(burdenset):
    obj_info = {
        'burdenset': {
            'name': burdenset.name,
            'uid': burdenset.uid,
            'creationTime': burdenset.created,
            'updateTime': burdenset.modified
        }
    }
    return obj_info

@timeit
def get_interv_set_fe_repr(interv_set):
    obj_info = {
        'intervset': {
            'name': interv_set.name,
            'uid': interv_set.uid,
            'creationTime': interv_set.created,
            'updateTime': interv_set.modified
        }
    }
    return obj_info

def get_package_set_fe_repr(packageset):
    obj_info = {
        'packageset': {
            'name': packageset.name,
            'uid': packageset.uid,
            'creationTime': packageset.created,
            'updateTime': packageset.modified
        }
    }
    return obj_info

#
# RPC functions
#

# RPC definitions
@register_RPC()
def get_version_info():
	''' Return the information about the project. '''
	gitinfo = sc.gitinfo(__file__)
	version_info = {
	       'version':   au.version,
	       'date':      au.versiondate,
	       'gitbranch': gitinfo['branch'],
	       'githash':   gitinfo['hash'],
	       'gitdate':   gitinfo['date'],
	}
	return version_info


##################################################################################
#%% Project RPCs
##################################################################################
    
@register_RPC(validation_type='nonanonymous user')
def get_scirisdemo_projects():
    """
    Return the projects associated with the Sciris Demo user.
    """
    
    # Get the user UID for the _ScirisDemo user.
    user_id = user.get_scirisdemo_user()
   
    # Get the prj.ProjectSO entries matching the _ScirisDemo user UID.
    project_entries = prj.proj_collection.get_project_entries_by_user(user_id)

    # Collect the project summaries for that user into a list.
    project_summary_list = map(load_project_summary_from_project_record, 
        project_entries)
    
    # Sort the projects by the project name.
    sorted_summary_list = sorted(project_summary_list, 
        key=lambda proj: proj['project']['name']) # Sorts by project name
    
    # Return a dictionary holding the project summaries.
    output = {'projects': sorted_summary_list}
    return output

@register_RPC(validation_type='nonanonymous user')
def load_project_summary(project_id):
    """
    Return the project summary, given the Project UID.
    """ 
    
    # Load the project record matching the UID of the project passed in.
    project_entry = load_project_record(project_id)
    
    # Return a project summary from the accessed prj.ProjectSO entry.
    return load_project_summary_from_project_record(project_entry)


@register_RPC(validation_type='nonanonymous user')
def load_current_user_project_summaries():
    """
    Return project summaries for all projects the user has to the client.
    """ 
    
    return load_current_user_project_summaries2()


@register_RPC(validation_type='nonanonymous user')
def load_all_project_summaries():
    """
    Return project summaries for all projects to the client.
    """ 
    
    # Get all of the prj.ProjectSO entries.
    project_entries = prj.proj_collection.get_all_objects()
    
    # Grab a list of project summaries from the list of prj.ProjectSO objects we 
    # just got.
    return {'projects': map(load_project_summary_from_project_record, 
        project_entries)}
            
@register_RPC(validation_type='nonanonymous user')    
def delete_projects(project_ids):
    """
    Delete all of the projects with the passed in UIDs.
    """ 
    
    # Loop over the project UIDs of the projects to be deleted...
    for project_id in project_ids:
        # Load the project record matching the UID of the project passed in.
        record = load_project_record(project_id, raise_exception=True)
        
        # If a matching record is found, delete the object from the 
        # ProjectCollection.
        if record is not None:
            prj.proj_collection.delete_object_by_uid(project_id)

@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_project(project_id):
    """
    For the passed in project UID, get the Project on the server, save it in a 
    file, minus results, and pass the full path of this file back.
    """
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s.prj' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    fileio.object_to_gzip_string_pickle_file(full_file_name, proj) # Write the object to a Gzip string pickle file.
    print(">> download_project %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.

@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_databook(project_id):
    """
    Download databook
    """
    N_POPS = 5
    print('WARNING, N_POPS HARDCODED')
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_databook.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.create_databook(full_file_name, num_pops=N_POPS)
    print(">> download_databook %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.


@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_progbook(project_id):
    """
    Download program book
    """
    N_PROGS = 5
    print("WARNING, PROGRAMS HARD_CODED")
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_program_book.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.make_progbook(full_file_name, progs=N_PROGS)
    print(">> download_databook %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.
    

@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_defaults(project_id):
    """
    Download defaults
    """
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_defaults.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.dataset().default_params.spreadsheet.save(full_file_name)
    print(">> download_defaults %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.


@register_RPC(call_type='download', validation_type='nonanonymous user')
def load_zip_of_prj_files(project_ids):
    """
    Given a list of project UIDs, make a .zip file containing all of these 
    projects as .prj files, and return the full path to this file.
    """
    
    # Use the downloads directory to put the file in.
    dirname = fileio.downloads_dir.dir_path

    # Build a list of prj.ProjectSO objects for each of the selected projects, 
    # saving each of them in separate .prj files.
    prjs = [load_project_record(id).save_as_file(dirname) for id in project_ids]
    
    # Make the zip file name and the full server file path version of the same..
    zip_fname = 'Projects %s.zip' % sc.getdate()
    server_zip_fname = os.path.join(dirname, sc.sanitizefilename(zip_fname))
    
    # Create the zip file, putting all of the .prj files in a projects 
    # directory.
    with ZipFile(server_zip_fname, 'w') as zipfile:
        for project in prjs:
            zipfile.write(os.path.join(dirname, project), 'projects/{}'.format(project))
            
    # Display the call information.
    # TODO: have this so that it doesn't show when logging is turned off
    print(">> load_zip_of_prj_files %s" % (server_zip_fname))

    # Return the server file name.
    return server_zip_fname

@register_RPC(validation_type='nonanonymous user')
def add_demo_project(user_id):
    """
    Add a demo Optima TB project
    """
    # Get a unique name for the project to be added.
    new_proj_name = get_unique_name('Demo project', other_names=None)
    
    # Create the project, loading in the desired spreadsheets.
    proj = au.demo(which='tb',do_plot=0) 
    proj.name = new_proj_name
    result = proj.results[0]
    proj.results = au.NDict()
    save_project_as_new(proj, user_id)
    store_result_separately(proj,result)
    
    # Display the call information.
    # TODO: have this so that it doesn't show when logging is turned off
    print(">> add_demo_project %s" % (proj.name))    
    
    # Save the new project in the DataStore.

    # Return the new project UID in the return message.
    return { 'projectId': str(proj.uid) }


@register_RPC(call_type='download', validation_type='nonanonymous user')
def create_new_project(user_id, proj_name, num_pops, data_start, data_end):
    """
    Create a new project.
    """
    
    args = {"num_pops":int(num_pops), "data_start":int(data_start), "data_end":int(data_end)}
    
    # Get a unique name for the project to be added.
    new_proj_name = get_unique_name(proj_name, other_names=None)
    
    # Create the project, loading in the desired spreadsheets.
    F = au.ProjectFramework(name='TB', filepath=au.atomica_path(['tests','frameworks'])+'framework_tb.xlsx')
    proj = au.Project(framework=F, name=new_proj_name)
    
    # Display the call information.
    # TODO: have this so that it doesn't show when logging is turned off
    print(">> create_new_project %s" % (proj.name))    
    
    # Save the new project in the DataStore.
    save_project_as_new(proj, user_id)
    
    # Use the downloads directory to put the file in.
    dirname = fileio.downloads_dir.dir_path
        
    # Create a filename containing the project name followed by a .prj 
    # suffix.
    file_name = '%s.xlsx' % proj.name
        
    # Generate the full file name with path.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name)
    
    # Return the databook
    proj.create_databook(databook_path=full_file_name, **args)
    
    print(">> download_databook %s" % (full_file_name))
    
    # Return the new project UID in the return message.
    return full_file_name


@register_RPC(call_type='upload', validation_type='nonanonymous user')
def upload_databook(databook_filename, project_id):
    """
    Upload a databook to a project.
    """
    print(">> upload_databook '%s'" % databook_filename)
    proj = load_project(project_id, raise_exception=True)
    proj.load_databook(databook_path=databook_filename, overwrite=True) 
    proj.modified = sc.today()
    save_project(proj) # Save the new project in the DataStore.
    return { 'projectId': str(proj.uid) } # Return the new project UID in the return message.


@register_RPC(call_type='upload', validation_type='nonanonymous user')
def upload_progbook(progbook_filename, project_id):
    """
    Upload a program book to a project.
    """
    print(">> upload_progbook '%s'" % progbook_filename)
    proj = load_project(project_id, raise_exception=True)
    proj.load_progbook(progbook_path=progbook_filename) 
    proj.modified = sc.today()
    save_project(proj)
    return { 'projectId': str(proj.uid) }


@register_RPC(validation_type='nonanonymous user')
def update_project_from_summary(project_summary):
    """
    Given the passed in project summary, update the underlying project 
    accordingly.
    """ 
    
    # Load the project corresponding with this summary.
    proj = load_project(project_summary['project']['id'])
       
    # Use the summary to set the actual project.
    proj.name = project_summary['project']['name']
    
    # Set the modified time to now.
    proj.modified = sc.today()
    
    # Save the changed project to the DataStore.
    save_project(proj)

@register_RPC(validation_type='nonanonymous user')
def copy_project(project_id):
    """
    Given a project UID, creates a copy of the project with a new UID and 
    returns that UID.
    """
    
    # Get the Project object for the project to be copied.
    project_record = load_project_record(project_id, raise_exception=True)
    proj = project_record.proj
    
    # Make a copy of the project loaded in to work with.
    new_project = sc.dcp(proj)
    
    # Just change the project name, and we have the new version of the 
    # Project object to be saved as a copy.
    new_project.name = get_unique_name(proj.name, other_names=None)
    
    # Set the user UID for the new projects record to be the current user.
    user_id = current_user.get_id() 
    
    # Display the call information.
    # TODO: have this so that it doesn't show when logging is turned off
    print(">> copy_project %s" % (new_project.name)) 
    
    # Save a DataStore projects record for the copy project.
    save_project_as_new(new_project, user_id)
    
    # Remember the new project UID (created in save_project_as_new()).
    copy_project_id = new_project.uid

    # Return the UID for the new projects record.
    return { 'projectId': copy_project_id }

@register_RPC(call_type='upload', validation_type='nonanonymous user')
def create_project_from_prj_file(prj_filename, user_id):
    """
    Given a .prj file name and a user UID, create a new project from the file 
    with a new UID and return the new UID.
    """
    
    # Display the call information.
    print(">> create_project_from_prj_file '%s'" % prj_filename)
    
    # Try to open the .prj file, and return an error message if this fails.
    try:
        proj = fileio.gzip_string_pickle_file_to_object(prj_filename)
    except Exception:
        return { 'error': 'BadFileFormatError' }
    
    # Reset the project name to a new project name that is unique.
    proj.name = get_unique_name(proj.name, other_names=None)
    
    # Save the new project in the DataStore.
    save_project_as_new(proj, user_id)
    
    # Return the new project UID in the return message.
    return { 'projectId': str(proj.uid) }




def supported_plots_func():
    
    supported_plots = {
            'Population size':'alive',
            'Latent infections':'lt_inf',
            'Active TB':'ac_inf',
            'Active DS-TB':'ds_inf',
            'Active MDR-TB':'mdr_inf',
            'Active XDR-TB':'xdr_inf',
            'New active DS-TB':{'New active DS-TB':['pd_div:flow','nd_div:flow']},
            'New active MDR-TB':{'New active MDR-TB':['pm_div:flow','nm_div:flow']},
            'New active XDR-TB':{'New active XDR-TB':['px_div:flow','nx_div:flow']},
            'Smear negative active TB':'sn_inf',
            'Smear positive active TB':'sp_inf',
            'Latent diagnoses':{'Latent diagnoses':['le_treat:flow','ll_treat:flow']},
            'New active TB diagnoses':{'Active TB diagnoses':['pd_diag:flow','pm_diag:flow','px_diag:flow','nd_diag:flow','nm_diag:flow','nx_diag:flow']},
            'New active DS-TB diagnoses':{'Active DS-TB diagnoses':['pd_diag:flow','nd_diag:flow']},
            'New active MDR-TB diagnoses':{'Active MDR-TB diagnoses':['pm_diag:flow','nm_diag:flow']},
            'New active XDR-TB diagnoses':{'Active XDR-TB diagnoses':['px_diag:flow','nx_diag:flow']},
            'Latent treatment':'ltt_inf',
            'Active treatment':'num_treat',
            'TB-related deaths':':ddis',
            }
    
    return supported_plots


@register_RPC(validation_type='nonanonymous user')    
def get_supported_plots(only_keys=False):
    
    supported_plots = supported_plots_func()
    
    if only_keys:
        return supported_plots.keys()
    else:
        return supported_plots


def get_plots(proj, result, plot_names=None, pops='all'):
    
    import pylab as pl
    
    supported_plots = supported_plots_func() 
    
    if plot_names is None: plot_names = supported_plots.keys()

    plot_names = sc.promotetolist(plot_names)

    graphs = []
    for plot_name in plot_names:
        try:
            plotdata = au.PlotData([result], outputs=supported_plots[plot_name], project=proj, pops=pops)
            figs = au.plot_series(plotdata, data=proj.data) # Todo - customize plot formatting here
            pl.gca().set_facecolor('none')
            for fig in figs:
                graph_dict = make_mpld3_graph_dict(fig)
                graphs.append(graph_dict)
            pl.close('all')
            print('Plot %s succeeded' % (plot_name))
        except Exception as E:
            print('WARNING: plot %s failed (%s)' % (plot_name, repr(E)))

    return {'graphs':graphs}


@register_RPC(validation_type='nonanonymous user')
def get_y_factors(project_id, parsetname=-1):
    print('Getting y factors...')
    y_factors = []
    proj = load_project(project_id, raise_exception=True)
    parset = proj.parsets[parsetname]
    for par_type in ["cascade", "comps", "characs"]:
        for parname in parset.par_ids[par_type].keys():
            thispar = parset.get_par(parname)
            if proj.framework.get_spec_value(parname, "can_calibrate"):
                for popname,y_factor in thispar.y_factor.items():
                    parlabel = proj.framework.get_spec_value(parname,'label')
                    poplabel = popname.capitalize() if popname.islower() else popname # proj.framework.get_spec_value(popname,'label')
                    thisdict = {'parname':parname, 'popname':popname, 'value':y_factor, 'parlabel':parlabel, 'poplabel':poplabel}
                    y_factors.append(thisdict)
                    print(thisdict)
    print('Returning %s y-factors' % len(y_factors))
    return y_factors


@timeit
@register_RPC(validation_type='nonanonymous user')    
def set_y_factors(project_id, y_factors, parsetname=-1):
    print('Setting y factors...')
    proj = load_project(project_id, raise_exception=True)
    parset = proj.parsets[parsetname]
    for par in y_factors:
        value = float(par['value'])
        parset.get_par(par['parname']).y_factor[par['popname']] = value
        if value != 1:
            print('Modified: %s' % par)
    
    proj.modified = sc.today()
    result = proj.run_sim(parset=parsetname, store_results=False)
    store_result_separately(proj, result)
    output = get_plots(proj,result)
    return output

@register_RPC(validation_type='nonanonymous user')    
def automatic_calibration(project_id, year=None, parsetname=-1):
    
    print('Running automatic calibration...')
    proj = load_project(project_id, raise_exception=True)
    
    print('Rerunning calibrated model...')
    proj.modified = sc.today()
    print('Resultsets before run: %s' % len(proj.results))
    proj.run_sim(parset=parsetname, store_results=True)
    print('Resultsets after run: %s' % len(proj.results))
    save_project(proj)    
    output = do_get_plots(proj.uid, year=year)
    return output


@register_RPC(validation_type='nonanonymous user')    
def run_default_scenario(project_id):
    
    import pylab as pl
    
    print('Running default scenario...')
    proj = load_project(project_id, raise_exception=True)
    
    scvalues = dict()

    scen_par = "spd_infxness"
    scen_pop = "15-64"
    scen_outputs = ["lt_inf", "ac_inf"]

    scvalues[scen_par] = dict()
    scvalues[scen_par][scen_pop] = dict()

    # Insert (or possibly overwrite) one value.
    scvalues[scen_par][scen_pop]["y"] = [0.125]
    scvalues[scen_par][scen_pop]["t"] = [2015.]
    scvalues[scen_par][scen_pop]["smooth_onset"] = [2]

    proj.make_scenario(name="varying_infections", instructions=scvalues)
    result1 = proj.run_scenario(scenario="varying_infections", parset="default", store_results = False, result_name="scen1")
    store_result_separately(proj, result1)

    # Insert two values and eliminate everything between them.
    scvalues[scen_par][scen_pop]["y"] = [0.125, 0.5]
    scvalues[scen_par][scen_pop]["t"] = [2015., 2020.]
    scvalues[scen_par][scen_pop]["smooth_onset"] = [2, 3]

    proj.make_scenario(name="varying_infections2", instructions=scvalues)
    result2 = proj.run_scenario(scenario="varying_infections2", parset="default", store_results = False, result_name="scen2")
    store_result_separately(proj, result2)

    figs = []
    graphs = []
    d = au.PlotData([result1,result2], outputs=scen_outputs, pops=[scen_pop])
    figs += au.plot_series(d, axis="results")
    pl.gca().set_facecolor('none')
    
    for f,fig in enumerate(figs):
        graph_dict = mpld3.fig_to_dict(fig)
        graphs.append(graph_dict)
        print('Converted figure %s of %s' % (f+1, len(figs)))
    
    print('Saving project...')
    save_project(proj)    
    return {'graphs':graphs}


@register_RPC(call_type='download', validation_type='nonanonymous user')
def export_results(project_id, resultset=-1):
    """
    Create a new framework.
    """
    print('Exporting results...')
    proj = load_project(project_id, raise_exception=True)
    result = proj.results[resultset]
    
    dirname = fileio.downloads_dir.dir_path 
    file_name = '%s.xlsx' % result.name 
    full_file_name = os.path.join(dirname, file_name)
    result.export(full_file_name)
    print(">> export_results %s" % (full_file_name))
    return full_file_name # Return the filename




##################################################################################
#%% Optimization functions and RPCs
##################################################################################

def rpc_optimize(proj=None, json=None):
    proj.make_optimization(json=json) # Make optimization
    optimized_result = proj.run_optimization(optimization=json['name']) # Run optimization
    return optimized_result

def py_to_js_optim(py_optim, prog_names):
    ''' Convert a Python to JSON representation of an optimization '''
    attrs = ['name', 'mults', 'add_funds']
    js_optim = {}
    for attr in attrs:
        js_optim[attr] = getattr(py_optim, attr) # Copy the attributes into a dictionary
    js_optim['obj'] = py_optim.obj[0]
    js_optim['spec'] = []
    for prog_name in prog_names:
        this_spec = {}
        this_spec['name'] = prog_name
        this_spec['included'] = True if prog_name in py_optim.prog_set else False
        this_spec['vals'] = []
        js_optim['spec'].append(this_spec)
    return js_optim
    

@register_RPC(validation_type='nonanonymous user')    
def get_optim_info(project_id):

    print('Getting optimization info...')
    proj = load_project(project_id, raise_exception=True)
    
    optim_summaries = []
    for py_optim in proj.optims.values():
        js_optim = py_to_js_optim(py_optim, proj.dataset().prog_names())
        optim_summaries.append(js_optim)
    
    print('JavaScript optimization info:')
    print(optim_summaries)

    return optim_summaries


@register_RPC(validation_type='nonanonymous user')    
def get_default_optim(project_id):

    print('Getting default optimization...')
    proj = load_project(project_id, raise_exception=True)
    
    py_optim = proj.demo_optims(doadd=False)[0]
    js_optim = py_to_js_optim(py_optim, proj.dataset().prog_names())
    js_optim['objective_options'] = ['thrive', 'child_deaths', 'stunting_prev', 'wasting_prev', 'anaemia_prev'] # WARNING, stick allowable optimization options here
    
    print('Created default JavaScript optimization:')
    print(js_optim)
    return js_optim



@register_RPC(validation_type='nonanonymous user')    
def set_optim_info(project_id, optim_summaries):

    print('Setting optimization info...')
    proj = load_project(project_id, raise_exception=True)
    proj.optims.clear()
    
    for j,js_optim in enumerate(optim_summaries):
        print('Setting optimization %s of %s...' % (j+1, len(optim_summaries)))
        json = sc.odict()
        json['name'] = js_optim['name']
        json['obj'] = js_optim['obj']
        jsm = js_optim['mults']
        if isinstance(jsm, list):
            vals = jsm
        elif sc.isstring(jsm):
            try:
                vals = [float(jsm)]
            except Exception as E:
                print('Cannot figure out what to do with multipliers "%s"' % jsm)
                raise E
        else:
            raise Exception('Cannot figure out multipliers type "%s" for "%s"' % (type(jsm), jsm))
        json['mults'] = vals
        json['add_funds'] = sc.sanitize(js_optim['add_funds'], forcefloat=True)
        json['prog_set'] = [] # These require more TLC
        for js_spec in js_optim['spec']:
            if js_spec['included']:
                json['prog_set'].append(js_spec['name'])
        
        print('Python optimization info for optimization %s:' % (j+1))
        print(json)
        
        proj.add_optim(json=json)
    
    print('Saving project...')
    save_project(proj)   
    
    return None


@register_RPC(validation_type='nonanonymous user')    
def run_optim(project_id, optim_name):
    
    print('Running optimization...')
    proj = load_project(project_id, raise_exception=True)
    
    proj.run_optims(keys=[optim_name], parallel=False)
    figs = proj.plot(toplot=['alloc']) # Only plot allocation
    graphs = []
    for f,fig in enumerate(figs.values()):
        for ax in fig.get_axes():
            ax.set_facecolor('none')
        graph_dict = mpld3.fig_to_dict(fig)
        graphs.append(graph_dict)
        print('Converted figure %s of %s' % (f+1, len(figs)))
    
    print('Saving project...')
    save_project(proj)    
    return {'graphs':graphs}


##################################################################################
#%% Miscellaneous RPCs
##################################################################################

@register_RPC(validation_type='nonanonymous user')    
def simulate_slow_rpc(sleep_secs, succeed=True):
    time.sleep(sleep_secs)
    
    if succeed:
        return 'success'
    else:
        return {'error': 'failure'}

