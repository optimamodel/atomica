"""
rpcs.py -- code related to HealthPrior project management
    
Last update: 2018jun04 by cliffk
"""

#
# Imports
#

import time
import os
import numpy as np
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
from . import frameworks as frw
from matplotlib.legend import Legend
import matplotlib.pyplot as pl
from matplotlib.pyplot import rc
rc('font', size=14)


def TickFormat():
    plugin = mpld3.plugins.MousePosition(fontsize=8, fmt='.4r')
    return plugin



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


label_mapping = {'SIR model':'sir',
                 'Tuberculosis':'tb',
                 'Diabetes':'diabetes',
                 'Service delivery':'service'}



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
    result_so = ResultSO(result)
    result_so.add_to_data_store()
    proj.results.append(ResultPlaceholder(result))
    save_project(proj)

# Dictionary to hold all of the registered RPCs in this module.
RPC_dict = {}

# RPC registration decorator factory created using call to make_register_RPC().
register_RPC = sw.make_register_RPC(RPC_dict)

label_mapping = {'SIR model':'sir',
                 'Tuberculosis':'tb',
                 'Diabetes':'diabetes',
                 'Service delivery':'service'}


###############################################################
#%% Framework functions
##############################################################
    

def load_framework_record(framework_id, raise_exception=True):
    """
    Return the framework DataStore reocord, given a framework UID.
    """ 
    
    # Load the matching frw.FrameworkSO object from the database.
    framework_record = frw.frame_collection.get_object_by_uid(framework_id)

    # If we have no match, we may want to throw an exception.
    if framework_record is None:
        if raise_exception:
            raise Exception('FrameworkDoesNotExist(id=%s)' % framework_id)
            
    # Return the Framework object for the match (None if none found).
    return framework_record

def load_framework(framework_id, raise_exception=True):
    """
    Return the Nutrition Framework object, given a framework UID, or None if no 
    ID match is found.
    """ 
    
    # Load the framework record matching the ID passed in.
    framework_record = load_framework_record(framework_id, 
        raise_exception=raise_exception)
    
    # If there is no match, raise an exception or return None.
    if framework_record is None:
        if raise_exception:
            raise Exception('FrameworkDoesNotExist(id=%s)' % framework_id)
        else:
            return None
        
    # Return the found framework.
    return framework_record.frame

def load_framework_summary_from_framework_record(framework_record):
    """
    Return the framework summary, given the DataStore record.
    """ 
    
    # Return the built framework summary.
    return framework_record.get_user_front_end_repr()
  
def load_current_user_framework_summaries2():
    """
    Return framework summaries for all frameworks the user has to the client. -- WARNING, fix!
    """ 
    
    # Get the frw.FrameworkSO entries matching the user UID.
    framework_entries = frw.frame_collection.get_framework_entries_by_user(current_user.get_id())
    
    # Grab a list of framework summaries from the list of frw.FrameworkSO objects we 
    # just got.
    return {'frameworks': map(load_framework_summary_from_framework_record, 
        framework_entries)}
                
def save_framework(frame):
    """
    Given a Framework object, wrap it in a new frw.FrameworkSO object and put this 
    in the framework collection (either adding a new object, or updating an 
    existing one)  skip_result lets you null out saved results in the Framework.
    """ 
    
    # Load the framework record matching the UID of the framework passed in.
    framework_record = load_framework_record(frame.uid)
    
    # Copy the framework, only save what we want...
    new_framework = sc.dcp(frame)
    new_framework.modified = sc.today()
         
    # Create the new framework entry and enter it into the FrameworkCollection.
    # Note: We don't need to pass in framework.uid as a 3rd argument because 
    # the constructor will automatically use the Framework's UID.
    frameSO = frw.FrameworkSO(new_framework, framework_record.owner_uid)
    frw.frame_collection.update_object(frameSO)
    

def save_framework_as_new(frame, user_id):
    """
    Given a Framework object and a user UID, wrap the Framework in a new frw.FrameworkSO 
    object and put this in the framework collection, after getting a fresh UID
    for this Framework.  Then do the actual save.
    """ 
    frame.uid = sc.uuid() # Set a new framework UID, so we aren't replicating the UID passed in.
    frameSO = frw.FrameworkSO(frame, user_id) # Create the new framework entry and enter it into the FrameworkCollection.
    frw.frame_collection.add_object(frameSO)  
    print(">> save_framework_as_new '%s'" % frame.name) # Display the call information.
    save_framework(frame) # Save the changed Framework object to the DataStore.
    return None




        
##############################################################
#%% Project functions
##############################################################
    

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
    proj.uid = sc.uuid() # Set a new project UID, so we aren't replicating the UID passed in.
    projSO = prj.ProjectSO(proj, user_id) # Create the new project entry and enter it into the ProjectCollection.
    prj.proj_collection.add_object(projSO)  
    print(">> save_project_as_new '%s'" % proj.name) # Display the call information.
    save_project(proj) # Save the changed Project object to the DataStore.
    return None



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
#%% Framework RPCs
##################################################################################

    
@register_RPC(validation_type='nonanonymous user')
def get_scirisdemo_frameworks():
    """
    Return the frameworks associated with the Sciris Demo user.
    """
    
    # Get the user UID for the _ScirisDemo user.
    user_id = user.get_scirisdemo_user()
   
    # Get the frw.FrameworkSO entries matching the _ScirisDemo user UID.
    framework_entries = frw.frame_collection.get_framework_entries_by_user(user_id)

    # Collect the framework summaries for that user into a list.
    framework_summary_list = map(load_framework_summary_from_framework_record, 
        framework_entries)
    
    # Sort the frameworks by the framework name.
    sorted_summary_list = sorted(framework_summary_list, 
        key=lambda frame: frame['framework']['name']) # Sorts by framework name
    
    # Return a dictionary holding the framework summaries.
    output = {'frameworks': sorted_summary_list}
    return output

@register_RPC(validation_type='nonanonymous user')
def load_framework_summary(framework_id):
    """
    Return the framework summary, given the Framework UID.
    """ 
    
    # Load the framework record matching the UID of the framework passed in.
    framework_entry = load_framework_record(framework_id)
    
    # Return a framework summary from the accessed frw.FrameworkSO entry.
    return load_framework_summary_from_framework_record(framework_entry)


@register_RPC(validation_type='nonanonymous user')
def load_current_user_framework_summaries():
    """
    Return framework summaries for all frameworks the user has to the client.
    """ 
    
    return load_current_user_framework_summaries2()


@register_RPC(validation_type='nonanonymous user')                
def load_all_framework_summaries():
    """
    Return framework summaries for all frameworks to the client.
    """ 
    
    # Get all of the frw.FrameworkSO entries.
    framework_entries = frw.frame_collection.get_all_objects()
    
    # Grab a list of framework summaries from the list of frw.FrameworkSO objects we 
    # just got.
    return {'frameworks': map(load_framework_summary_from_framework_record, 
        framework_entries)}
            
@register_RPC(validation_type='nonanonymous user')    
def delete_frameworks(framework_ids):
    """
    Delete all of the frameworks with the passed in UIDs.
    """ 
    
    # Loop over the framework UIDs of the frameworks to be deleted...
    for framework_id in framework_ids:
        # Load the framework record matching the UID of the framework passed in.
        record = load_framework_record(framework_id, raise_exception=True)
        
        # If a matching record is found, delete the object from the 
        # FrameworkCollection.
        if record is not None:
            frw.frame_collection.delete_object_by_uid(framework_id)

@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_framework(framework_id):
    """
    For the passed in framework UID, get the Framework on the server, save it in a 
    file, minus results, and pass the full path of this file back.
    """
    frame = load_framework(framework_id, raise_exception=True) # Load the framework with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s.frw' % frame.name # Create a filename containing the framework name followed by a .frw suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    fileio.object_to_gzip_string_pickle_file(full_file_name, frame) # Write the object to a Gzip string pickle file.
    print(">> download_framework %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.


@register_RPC(call_type='download', validation_type='nonanonymous user')
def load_zip_of_frw_files(framework_ids):
    """
    Given a list of framework UIDs, make a .zip file containing all of these 
    frameworks as .frw files, and return the full path to this file.
    """
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    frws = [load_framework_record(id).save_as_file(dirname) for id in framework_ids] # Build a list of frw.FrameworkSO objects for each of the selected frameworks, saving each of them in separate .frw files.
    zip_fname = 'Frameworks %s.zip' % sc.getdate() # Make the zip file name and the full server file path version of the same..
    server_zip_fname = os.path.join(dirname, sc.sanitizefilename(zip_fname))
    with ZipFile(server_zip_fname, 'w') as zipfile: # Create the zip file, putting all of the .frw files in a frameworks directory.
        for framework in frws:
            zipfile.write(os.path.join(dirname, framework), 'frameworks/{}'.format(framework))
    print(">> load_zip_of_frw_files %s" % (server_zip_fname)) # Display the call information.
    return server_zip_fname # Return the server file name.


@register_RPC(validation_type='nonanonymous user')
def add_demo_framework(user_id, framework_name):
    """
    Add a demo framework
    """
    try:
        which = label_mapping[framework_name]
    except Exception:
        errormsg = 'Invalid demo framework name, must be one of "%s", not "%s"' % (label_mapping.keys(), framework_name)
        raise Exception(errormsg)
    other_names = [frw['framework']['name'] for frw in load_current_user_framework_summaries2()['frameworks']]
    new_frame_name = get_unique_name(framework_name, other_names=other_names) # Get a unique name for the framework to be added.
    frame = au.demo(kind='framework', which=which)  # Create the framework, loading in the desired spreadsheets.
    frame.name = new_frame_name
    print(">> add_demo_framework %s" % (frame.name))    
    save_framework_as_new(frame, user_id) # Save the new framework in the DataStore.
    return { 'frameworkId': str(frame.uid) } # Return the new framework UID in the return message.


@register_RPC(call_type='download', validation_type='nonanonymous user')
def create_new_framework():
    """
    Create a new framework.
    """
    filename = 'framework_template.xlsx'
    filepath = au.atomica_path(['atomica','core'])+filename
    print(">> download_framework %s" % (filepath))
    return filepath # Return the filename


@register_RPC(call_type='upload', validation_type='nonanonymous user')
def upload_frameworkbook(databook_filename, framework_id):
    """
    Upload a databook to a framework.
    """
    
    # Display the call information.
    print(">> upload_databook '%s'" % databook_filename)
    
    frame = load_framework(framework_id, raise_exception=True)
    
    # Reset the framework name to a new framework name that is unique.
    frame.read_from_file(filepath=databook_filename, overwrite=True)
    frame.modified = sc.today()
    
    # Save the new framework in the DataStore.
    save_framework(frame)
    
    # Return the new framework UID in the return message.
    return { 'frameworkId': str(frame.uid) }


@register_RPC(validation_type='nonanonymous user')
def update_framework_from_summary(framework_summary):
    """
    Given the passed in framework summary, update the underlying framework accordingly.
    """ 
    frame = load_framework(framework_summary['framework']['id']) # Load the framework corresponding with this summary.
    frame_uid = sc.uuid(framework_summary['framework']['id']).hex # Use the summary to set the actual framework, checking to make sure that the framework name is unique.
    other_names = [frw['framework']['name'] for frw in load_current_user_framework_summaries2()['frameworks'] if (frw['framework']['id'].hex != frame_uid)]
    frame.name = get_unique_name(framework_summary['framework']['name'], other_names=other_names)
    frame.modified = sc.today() # Set the modified time to now.
    save_framework(frame) # Save the changed framework to the DataStore.
    return None
    
@register_RPC(validation_type='nonanonymous user')    
def copy_framework(framework_id):
    """
    Given a framework UID, creates a copy of the framework with a new UID and returns that UID.
    """
    framework_record = load_framework_record(framework_id, raise_exception=True) # Get the Framework object for the framework to be copied.
    frame = framework_record.frame
    new_framework = sc.dcp(frame) # Make a copy of the framework loaded in to work with.
    other_names = [frw['framework']['name'] for frw in load_current_user_framework_summaries2()['frameworks']] # Just change the framework name, and we have the new version of the Framework object to be saved as a copy
    new_framework.name = get_unique_name(frame.name, other_names=other_names)
    user_id = current_user.get_id()  # Set the user UID for the new frameworks record to be the current user.
    print(">> copy_framework %s" % (new_framework.name))  # Display the call information.
    save_framework_as_new(new_framework, user_id) # Save a DataStore frameworks record for the copy framework.
    copy_framework_id = new_framework.uid # Remember the new framework UID (created in save_framework_as_new()).
    return { 'frameworkId': copy_framework_id } # Return the UID for the new frameworks record.


@register_RPC(call_type='upload', validation_type='nonanonymous user')
def create_framework_from_frw_file(frw_filename, user_id):
    """
    Given a .frw file name and a user UID, create a new framework from the file 
    with a new UID and return the new UID.
    """
    print(">> create_framework_from_frw_file '%s'" % frw_filename)
    print('Trying to open the file')
    try: # Try to open the .frw file, and return an error message if this fails.
        frame = fileio.gzip_string_pickle_file_to_object(frw_filename)
    except Exception as E:
        print('ERROR, load failed: %s' % repr(E))
        return { 'error': 'BadFileFormatError' }
    other_names = [frw['framework']['name'] for frw in load_current_user_framework_summaries2()['frameworks']] # Reset the framework name to a new framework name that is unique.
    frame.name = get_unique_name(frame.name, other_names=other_names)
    save_framework_as_new(frame, user_id) # Save the new framework in the DataStore.
    print('Created new framework %s, uid:%s' % (frame.name, frame.uid))
    return { 'frameworkId': str(frame.uid) }






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
def download_framework_from_project(project_id):
    """
    Download databook
    """
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_framework.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.framework.save(full_file_name)
    print(">> download_databook %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.



@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_databook(project_id):
    """
    Download databook
    """
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_databook.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.databook.save(full_file_name)
    print(">> download_databook %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.


@register_RPC(call_type='download', validation_type='nonanonymous user')   
def download_progbook(project_id):
    """ Download program book """
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_program_book.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.progbook.save(full_file_name)
    print(">> download_progbook %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.
  
    
@register_RPC(call_type='download', validation_type='nonanonymous user')   
def create_progbook(project_id, num_progs):
    """ Create program book """
    proj = load_project(project_id, raise_exception=True) # Load the project with the matching UID.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s_program_book.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.make_progbook(progbook_path=full_file_name, progs=int(num_progs))
    print(">> download_progbook %s" % (full_file_name)) # Display the call information.
    return full_file_name # Return the full filename.    
    


@register_RPC(call_type='download', validation_type='nonanonymous user')
def load_zip_of_prj_files(project_ids):
    """
    Given a list of project UIDs, make a .zip file containing all of these 
    projects as .prj files, and return the full path to this file.
    """
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    prjs = [load_project_record(id).save_as_file(dirname) for id in project_ids] # Build a list of prj.ProjectSO objects for each of the selected projects, saving each of them in separate .prj files.
    zip_fname = 'Projects %s.zip' % sc.getdate() # Make the zip file name and the full server file path version of the same..
    server_zip_fname = os.path.join(dirname, sc.sanitizefilename(zip_fname))
    with ZipFile(server_zip_fname, 'w') as zipfile: # Create the zip file, putting all of the .prj files in a projects directory.
        for project in prjs:
            zipfile.write(os.path.join(dirname, project), 'projects/{}'.format(project))
    print(">> load_zip_of_prj_files %s" % (server_zip_fname)) # Display the call information.
    return server_zip_fname # Return the server file name.


@register_RPC(validation_type='nonanonymous user')
def add_demo_project(user_id, project_name='default'):
    """
    Add a demo project
    """
    if project_name is 'default':
        new_proj_name = get_unique_name('Demo project', other_names=None) # Get a unique name for the project to be added
        proj = au.demo(which='tb', do_run=False, do_plot=False)  # Create the project, loading in the desired spreadsheets.
        proj.name = new_proj_name
    else:
        try:
            which = label_mapping[project_name]
            new_proj_name = get_unique_name(project_name, other_names=None) # Get a unique name for the project to be added.
            proj = au.demo(which=which, do_run=False, do_plot=False)  # Create the project, loading in the desired spreadsheets.
            proj.name = new_proj_name
            print('Adding demo project %s/%s...' % (project_name, which))
        except Exception as E:
            errormsg = 'Invalid demo framework name, must be one of "%s", not "%s": %s' % (label_mapping.keys(), project_name, repr(E))
            raise Exception(errormsg)

    save_project_as_new(proj, user_id) # Save the new project in the DataStore.
    print(">> add_demo_project %s" % (proj.name))    
    return { 'projectId': str(proj.uid) } # Return the new project UID in the return message.


@register_RPC(call_type='download', validation_type='nonanonymous user')
def create_new_project(user_id, proj_name, num_pops, num_progs, data_start, data_end):
    """
    Create a new project.
    """
    args = {"num_pops":int(num_pops), "data_start":int(data_start), "data_end":int(data_end)}
    new_proj_name = get_unique_name(proj_name, other_names=None) # Get a unique name for the project to be added.
    F = au.ProjectFramework(name=new_proj_name , inputs=au.atomica_path(['tests','frameworks'])+'framework_tb.xlsx')
    proj = au.Project(framework=F, name=new_proj_name) # Create the project, loading in the desired spreadsheets.
    print(">> create_new_project %s" % (proj.name))    
    save_project_as_new(proj, user_id) # Save the new project in the DataStore.
    dirname = fileio.downloads_dir.dir_path # Use the downloads directory to put the file in.
    file_name = '%s.xlsx' % proj.name # Create a filename containing the project name followed by a .prj suffix.
    full_file_name = '%s%s%s' % (dirname, os.sep, file_name) # Generate the full file name with path.
    proj.create_databook(databook_path=full_file_name, **args) # Return the databook
    print(">> download_databook %s" % (full_file_name))
    return full_file_name # Return the filename


@register_RPC(call_type='upload', validation_type='nonanonymous user')
def upload_databook(databook_filename, project_id):
    """
    Upload a databook to a project.
    """
    print(">> upload_databook '%s'" % databook_filename)
    proj = load_project(project_id, raise_exception=True)
    proj.load_databook(databook_path=databook_filename) 
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
    proj = load_project(project_summary['project']['id']) # Load the project corresponding with this summary.
    proj.name = project_summary['project']['name'] # Use the summary to set the actual project.
    proj.modified = sc.today() # Set the modified time to now.
    save_project(proj) # Save the changed project to the DataStore.
    return

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







@register_RPC(validation_type='nonanonymous user')
def get_y_factors(project_id, parsetname=-1):
    print('Getting y factors for parset %s...' % parsetname)
    TEMP_YEAR = 2018 # WARNING, hard-coded!
    y_factors = []
    proj = load_project(project_id, raise_exception=True)
    parset = proj.parsets[parsetname]
    count = 0
    for par_type in ["cascade", "comps", "characs"]:
        for parname in parset.par_ids[par_type].keys():
            this_par = parset.get_par(parname)
            this_spec = proj.framework.get_variable(parname)[0]
            if 'Can Calibrate' in this_spec and this_spec['Can Calibrate'] == 'y':
                for popname,y_factor in this_par.y_factor.items():
                    count += 1
                    parlabel = this_spec['Display Name']
                    popindex = parset.pop_names.index(popname)
                    poplabel = parset.pop_labels[popindex]
                    try:    
                        interp_val = this_par.interpolate([TEMP_YEAR],popname)[0]
                        if not np.isfinite(interp_val):
                            interp_val = 1
                        if sc.approx(interp_val, 0):
                            interp_val = 1
                    except: 
                        interp_val = 1
                    dispvalue = interp_val*y_factor
                    thisdict = {'index':count, 'parname':parname, 'popname':popname, 'value':y_factor, 'dispvalue':dispvalue, 'parlabel':parlabel, 'poplabel':poplabel}
                    y_factors.append(thisdict)
                    print(thisdict)
    print('Returning %s y-factors' % len(y_factors))
    return y_factors


@timeit
@register_RPC(validation_type='nonanonymous user')    
def set_y_factors(project_id, parsetname=-1, y_factors=None, plot_options=None, start_year=None, end_year=None, plot_type=None):
    print('Setting y factors for parset %s...' % parsetname)
    TEMP_YEAR = 2018 # WARNING, hard-coded!
    proj = load_project(project_id, raise_exception=True)
    parset = proj.parsets[parsetname]
    for pardict in y_factors:
        parname   = pardict['parname']
        dispvalue = float(pardict['dispvalue'])
        popname   = pardict['popname']
        thispar   = parset.get_par(parname)
        try:    
            interp_val = thispar.interpolate([TEMP_YEAR],popname)[0]
            if not np.isfinite(interp_val):
                interp_val = 1
            if sc.approx(interp_val, 0):
                interp_val = 1
        except: 
            interp_val = 1
        y_factor  = dispvalue/interp_val
        parset.get_par(parname).y_factor[popname] = y_factor
        if not sc.approx(y_factor, 1):
            print('Modified: %s (%s)' % (parname, y_factor))
    
    proj.modified = sc.today()
    result = proj.run_sim(parset=parsetname, store_results=False)
    store_result_separately(proj, result)
    if plot_type in ['cascade', 'multi_cascade']:
        output = get_cascade_plot(proj, results=result, pops=None, year=float(end_year), plot_type=plot_type)
    else:
        output = get_calibration_plots(proj, result, pops=None, plot_options=plot_options, stacked=True, xlims=(float(start_year), float(end_year)))
        # Commands below will render unstacked plots with data, and will interleave them so they appear next to each other in the FE
        unstacked_output = get_calibration_plots(proj, result, pops=None, plot_options=plot_options, stacked=False, xlims=(float(start_year), float(end_year)))
        output['graphs'] = [x for t in zip(output['graphs'], unstacked_output['graphs']) for x in t]
    return output




#%% Plotting
def supported_plots_func():
    supported_plots = sc.odict() # Preserve order
    supported_plots['Population size'] = 'alive'
    supported_plots['Latent infections'] = 'lt_inf'
    supported_plots['Active TB'] = 'ac_inf'
    supported_plots['Active DS-TB'] = 'ds_inf'
    supported_plots['Active MDR-TB'] = 'mdr_inf'
    supported_plots['Active XDR-TB'] = 'xdr_inf'
    supported_plots['New active DS-TB'] = ['pd_div:flow','nd_div:flow']
    supported_plots['New active MDR-TB'] = ['pm_div:flow','nm_div:flow']
    supported_plots['New active XDR-TB'] = ['px_div:flow','nx_div:flow']
    supported_plots['Smear negative active TB'] = 'sn_inf'
    supported_plots['Smear positive active TB'] = 'sp_inf'
    supported_plots['Latent diagnoses'] = ['le_treat:flow','ll_treat:flow']
    supported_plots['New active TB diagnoses'] = ['pd_diag:flow','pm_diag:flow','px_diag:flow','nd_diag:flow','nm_diag:flow','nx_diag:flow']
    supported_plots['New active DS-TB diagnoses'] = ['pd_diag:flow','nd_diag:flow']
    supported_plots['New active MDR-TB diagnoses'] = ['pm_diag:flow','nm_diag:flow']
    supported_plots['New active XDR-TB diagnoses'] = ['px_diag:flow','nx_diag:flow']
    supported_plots['Latent treatment'] = 'ltt_inf'
    supported_plots['Active treatment'] = 'num_treat'
    supported_plots['TB-related deaths'] = ':ddis'
    return supported_plots

@register_RPC(validation_type='nonanonymous user')    
def get_supported_plots(only_keys=False):
    supported_plots = supported_plots_func()
    if only_keys:
        plot_names = supported_plots.keys()
        vals = np.ones(len(plot_names))
        output = []
        for plot_name,val in zip(plot_names,vals):
            this = {'plot_name':plot_name, 'active':val}
            output.append(this)
        return output
    else:
        return supported_plots


def get_calibration_plots(proj, result, plot_names=None, pops=None, plot_options=None, outputs=None, replace_nans=True, stacked=False, xlims=None):
    # Plot calibration - only one result is permitted, and the axis is guaranteed to be pops
    supported_plots = supported_plots_func()
    if plot_names is None: 
        if plot_options is not None:
            plot_names = []
            for item in plot_options:
                if item['active']: plot_names.append(item['plot_name'])
        else:
            plot_names = supported_plots.keys()
    plot_names = sc.promotetolist(plot_names)
    if outputs is None:
        outputs = [{plot_name:supported_plots[plot_name]} for plot_name in plot_names]
    graphs = []
    for output in outputs:
        try:
            if isinstance(output.values()[0],list):
                plotdata = au.PlotData(result, outputs=output, project=proj, pops=pops)
            else:
                plotdata = au.PlotData(result, outputs=output.values()[0], project=proj, pops=pops) # Don't rename the plot, this will allow data to be retrieved

            nans_replaced = 0
            for series in plotdata.series:
                if replace_nans and any(np.isnan(series.vals)):
                    nan_inds = sc.findinds(np.isnan(series.vals))
                    for nan_ind in nan_inds:
                        if nan_ind>0: # Skip the first point
                            series.vals[nan_ind] = series.vals[nan_ind-1]
                            nans_replaced += 1
            if nans_replaced:
                print('Warning: %s nans were replaced' % nans_replaced)

            if stacked:
                figs = au.plot_series(plotdata, axis='pops', plot_type='stacked')
            else:
                figs = au.plot_series(plotdata, axis='pops', data=proj.data) # Only plot data if not stacked

            for fig in figs:
                ax = fig.get_axes()[0]
                ax.set_facecolor('none')
                ax.set_title(output.keys()[0]) # This is in a loop over outputs, so there should only be one output present
                ax.set_ylabel(plotdata.series[0].units) # All outputs should have the same units (one output for each pop/result)
                if xlims is not None: ax.set_xlim(xlims)
                fig.tight_layout(rect=[0.05,0.05,0.9,0.95])
                mpld3.plugins.connect(fig, TickFormat())
                graph_dict = mpld3.fig_to_dict(fig)
                graphs.append(graph_dict)
            pl.close('all')
            print('Plot %s succeeded' % (output))
        except Exception as E:
            print('WARNING: plot %s failed (%s)' % (output, repr(E)))


    return {'graphs':graphs}


def get_plots(proj, results=None, plot_names=None, plot_options=None, pops='all', outputs=None, do_plot_data=None, replace_nans=True,stacked=False, xlims=None):
    results = sc.promotetolist(results)
    supported_plots = supported_plots_func() 
    if plot_names is None: 
        if plot_options is not None:
            plot_names = []
            for item in plot_options:
                if item['active']: plot_names.append(item['plot_name'])
        else:
            plot_names = supported_plots.keys()
    plot_names = sc.promotetolist(plot_names)
    if outputs is None:
        outputs = [{plot_name:supported_plots[plot_name]} for plot_name in plot_names]
    graphs = []
    data = proj.data if do_plot_data is not False else None # Plot data unless asked not to
    for output in outputs:
        try:

            if isinstance(output.values()[0],list):
                plotdata = au.PlotData(results, outputs=output, project=proj, pops=pops)
            else:
                # Pass string in directly so that it is not treated as a function aggregation
                plotdata = au.PlotData(results, outputs=output.values()[0], project=proj, pops=pops)

            nans_replaced = 0
            for series in plotdata.series:
                if replace_nans and any(np.isnan(series.vals)):
                    nan_inds = sc.findinds(np.isnan(series.vals))
                    for nan_ind in nan_inds:
                        if nan_ind>0: # Skip the first point
                            series.vals[nan_ind] = series.vals[nan_ind-1]
                            nans_replaced += 1
            if nans_replaced: print('Warning: %s nans were replaced' % nans_replaced)
            if stacked: figs = au.plot_series(plotdata, data=data, axis='pops', plot_type='stacked')
            else:       figs = au.plot_series(plotdata, data=data, axis='results')

            # Todo - customize plot formatting here
            for fig in figs:
                ax = fig.get_axes()[0]
                ax.set_facecolor('none')
                ax.set_title(output.keys()[0]) # This is in a loop over outputs, so there should only be one output present
                ax.set_ylabel(plotdata.series[0].units) # All outputs should have the same units (one output for each pop/result)
                if xlims is not None: ax.set_xlim(xlims)
                legend = fig.findobj(Legend)[0]
                if len(legend.get_texts())==1:
                    legend.remove() # Can remove the legend if it only has one entry
                fig.tight_layout(rect=[0.05,0.05,0.9,0.95])
                mpld3.plugins.connect(fig, TickFormat())
                graph_dict = mpld3.fig_to_dict(fig)
                graphs.append(graph_dict)
            # pl.close('all')
            print('Plot %s succeeded' % (output))
        except Exception as E:
            print('WARNING: plot %s failed (%s)' % (output, repr(E)))
    return {'graphs':graphs}


def get_cascade_plot(proj, results=None, pops=None, year=None, plot_type=None):
    graphs = []
    if plot_type == 'cascade':
        fig = au.plot_cascade(results, cascade='main', pops=pops, year=year)
    elif plot_type == 'multi_cascade':
        fig = au.plot_multi_cascade(results, cascade='main', pops=pops, year=[year])
    figs = sc.promotetolist(fig)
    for fig in figs:
        ax = fig.get_axes()[0]
        ax.set_facecolor('none')
        fig.tight_layout(rect=[0.05,0.05,0.9,0.95])
        mpld3.plugins.connect(fig, TickFormat())
        graph_dict = mpld3.fig_to_dict(fig)
        graphs.append(graph_dict)
    print('Cascade plot succeeded')
    return {'graphs':graphs}
    

@register_RPC(validation_type='nonanonymous user')    
def automatic_calibration(project_id, parsetname=-1, max_time=20, saveresults=False):
    
    print('Running automatic calibration for parset %s...' % parsetname)
    proj = load_project(project_id, raise_exception=True)
    proj.calibrate(max_time=max_time) # WARNING, add kwargs!
    
    print('Rerunning calibrated model...')
    
    print('Resultsets before run: %s' % len(proj.results))
    if saveresults:
        result = proj.run_sim(parset=parsetname, store_results=True)
        save_project(proj)
    else:
        result = proj.run_sim(parset=parsetname, store_results=False) 
        store_result_separately(proj, result)
    print('Resultsets after run: %s' % len(proj.results))

    output = get_calibration_plots(proj, result,pops=None,stacked=True)

    # Commands below will render unstacked plots with data, and will interleave them
    # so they appear next to each other in the FE
    print('WARNING UPDATE')
    unstacked_output = get_calibration_plots(proj, result,pops=None,stacked=False)
    output['graphs'] = [x for t in zip(output['graphs'], unstacked_output['graphs']) for x in t]

    return output


@register_RPC(call_type='download', validation_type='nonanonymous user')
def export_results(project_id, resultset=-1):
    """
    Create a new framework.
    """
    print('Exporting results...')
    proj = load_project(project_id, raise_exception=True)
    result = proj.results[resultset]
    if isinstance(result, ResultPlaceholder):
        print('Getting actual result...')
        result = result.get()
    
    dirname = fileio.downloads_dir.dir_path 
    file_name = '%s.xlsx' % result.name 
    full_file_name = os.path.join(dirname, file_name)
    result.export(full_file_name)
    print(">> export_results %s" % (full_file_name))
    return full_file_name # Return the filename


##################################################################################
#%% Parset functions and RPCs
##################################################################################

#TO_PORT
@register_RPC(validation_type='nonanonymous user') 
def get_parset_info(project_id):
    print('Returning parset info...')
    proj = load_project(project_id, raise_exception=True)
    parset_names = proj.parsets.keys()
    return parset_names

#TO_PORT
@register_RPC(validation_type='nonanonymous user') 
def rename_parset(project_id, parsetname=None, new_name=None):
    print('Renaming parset from %s to %s...' % (parsetname, new_name))
    proj = load_project(project_id, raise_exception=True)
    proj.parsets.rename(parsetname, new_name)
    print('Saving project...')
    save_project(proj)
    return None

#TO_PORT
@register_RPC(validation_type='nonanonymous user') 
def copy_parset(project_id, parsetname=None):
    print('Copying parset %s...' % parsetname)
    proj = load_project(project_id, raise_exception=True)
    print('Number of parsets before copy: %s' % len(proj.parsets))
    new_name = get_unique_name(parsetname, other_names=proj.parsets.keys())
    print('Old name: %s; new name: %s' % (parsetname, new_name))
    proj.parsets[new_name] = sc.dcp(proj.parsets[parsetname])
    print('Number of parsets after copy: %s' % len(proj.parsets))
    print('Saving project...')
    save_project(proj)
    return None

#TO_PORT
@register_RPC(validation_type='nonanonymous user') 
def delete_parset(project_id, parsetname=None):
    print('Deleting parset %s...' % parsetname)
    proj = load_project(project_id, raise_exception=True)
    print('Number of parsets before delete: %s' % len(proj.parsets))
    if len(proj.parsets)>1:
        proj.parsets.pop(parsetname)
    else:
        raise Exception('Cannot delete last parameter set')
    print('Number of parsets after delete: %s' % len(proj.parsets))
    print('Saving project...')
    save_project(proj)
    return None

##################################################################################
#%% Progset functions and RPCs
##################################################################################

@register_RPC(validation_type='nonanonymous user') 
def get_progset_info(project_id):
    print('Returning progset info...')
    proj = load_project(project_id, raise_exception=True)
    progset_names = proj.progsets.keys()
    return progset_names


@register_RPC(validation_type='nonanonymous user') 
def rename_progset(project_id, progsetname=None, new_name=None):
    print('Renaming progset from %s to %s...' % (progsetname, new_name))
    proj = load_project(project_id, raise_exception=True)
    proj.progsets.rename(progsetname, new_name)
    print('Saving project...')
    save_project(proj)
    return None


@register_RPC(validation_type='nonanonymous user') 
def copy_progset(project_id, progsetname=None):
    print('Copying progset %s...' % progsetname)
    proj = load_project(project_id, raise_exception=True)
    print('Number of progsets before copy: %s' % len(proj.progsets))
    new_name = get_unique_name(progsetname, other_names=proj.progsets.keys())
    print('Old name: %s; new name: %s' % (progsetname, new_name))
    proj.progsets[new_name] = sc.dcp(proj.progsets[progsetname])
    print('Number of progsets after copy: %s' % len(proj.progsets))
    print('Saving project...')
    save_project(proj)
    return None


@register_RPC(validation_type='nonanonymous user') 
def delete_progset(project_id, progsetname=None):
    print('Deleting progset %s...' % progsetname)
    proj = load_project(project_id, raise_exception=True)
    print('Number of progsets before delete: %s' % len(proj.progsets))
    if len(proj.progsets)>1:
        proj.progsets.pop(progsetname)
    else:
        raise Exception('Cannot delete last program set')
    print('Number of progsets after delete: %s' % len(proj.progsets))
    print('Saving project...')
    save_project(proj)
    return None


##################################################################################
#%% Scenario functions and RPCs
##################################################################################

def py_to_js_scen(py_scen, project=None):
    ''' Convert a Python to JSON representation of a scenario. The Python scenario might be a dictionary or an object. '''
    js_scen = {}
    attrs = ['name', 'parsetname', 'progsetname', 'start_year'] 
    for attr in attrs:
        if isinstance(py_scen, dict):
            js_scen[attr] = py_scen[attr] # Copy the attributes directly
            
        else:
            js_scen[attr] = getattr(py_scen, attr) # Copy the attributes into a dictionary
            
    js_scen['alloc'] = []
    if isinstance(py_scen, dict): alloc = py_scen['alloc']
    else:                         alloc = py_scen.alloc
    for prog_name,budget in alloc.items():
        prog_label = project.progset().programs[prog_name].label
        if sc.isiterable(budget):
            if len(budget)>1:
                raise Exception('Budget should only have a single element in it, not %s' % len(budget))
            else:
                budget = budget[0] # If it's not a scalar, pull out the first element -- WARNING, KLUDGY
        js_scen['alloc'].append([prog_name,round(float(budget)), prog_label])
    return js_scen

def js_to_py_scen(js_scen):
    ''' Convert a Python to JSON representation of a scenario '''
    py_scen = sc.odict()
    attrs = ['name', 'parsetname', 'progsetname'] 
    for attr in attrs:
        py_scen[attr] = js_scen[attr] # Copy the attributes into a dictionary
    py_scen['start_year'] = float(js_scen['start_year']) # Convert to number
    py_scen['alloc'] = sc.odict()
    for item in js_scen['alloc']:
        prog_name = item[0]
        budget = item[1]
        if sc.isstring(budget):
            try:
                budget = to_number(budget)
            except Exception as E:
                raise Exception('Could not convert budget to number: %s' % repr(E))
        if sc.isiterable(budget):
            if len(budget)>1:
                raise Exception('Budget should only have a single element in it, not %s' % len(budget))
            else:
                budget = budget[0] # If it's not a scalar, pull out the first element -- WARNING, KLUDGY
        py_scen['alloc'][prog_name] = to_number(budget)
    return py_scen
    

@register_RPC(validation_type='nonanonymous user')    
def get_scen_info(project_id):
    print('Getting scenario info...')
    proj = load_project(project_id, raise_exception=True)
    scenario_summaries = []
    for py_scen in proj.scens.values():
        js_scen = py_to_js_scen(py_scen, project=proj)
        scenario_summaries.append(js_scen)
    print('JavaScript scenario info:')
    print(scenario_summaries)
    return scenario_summaries


@register_RPC(validation_type='nonanonymous user')    
def set_scen_info(project_id, scenario_summaries):
    print('Setting scenario info...')
    proj = load_project(project_id, raise_exception=True)
    proj.scens.clear()
    for j,js_scen in enumerate(scenario_summaries):
        print('Setting scenario %s of %s...' % (j+1, len(scenario_summaries)))
        py_scen = js_to_py_scen(js_scen)
        print('Python scenario info for scenario %s:' % (j+1))
        print(py_scen)
        proj.make_scenario(which='budget', json=py_scen)
    print('Saving project...')
    save_project(proj)
    return None


@register_RPC(validation_type='nonanonymous user')    
def get_default_budget_scen(project_id):
    print('Creating default scenario...')
    proj = load_project(project_id, raise_exception=True)
    py_scen = proj.demo_scenarios(doadd=False)
    js_scen = py_to_js_scen(py_scen, project=proj)
    print('Created default JavaScript scenario:')
    print(js_scen)
    return js_scen


def sanitize(vals, skip=False, forcefloat=False):
    ''' Make sure values are numeric, and either return nans or skip vals that aren't '''
    if sc.isiterable(vals):
        as_array = False if forcefloat else True
    else:
        vals = [vals]
        as_array = False
    output = []
    for val in vals:
        if val=='':
            sanival = np.nan
        elif val==None:
            sanival = np.nan
        else:
            try:
                sanival = float(val)
            except Exception as E:
                print('Could not sanitize value "%s": %s; returning nan' % (val, repr(E)))
                sanival = np.nan
        if skip and not np.isnan(sanival):
            output.append(sanival)
        else:
            output.append(sanival)
    if as_array:
        return output
    else:
        return output[0]
    
    

@register_RPC(validation_type='nonanonymous user')    
def run_scenarios(project_id, plot_options, saveresults=False, plot_type=None):
    print('Running scenarios...')
    proj = load_project(project_id, raise_exception=True)
    results = proj.run_scenarios()
    if plot_type == 'multi_cascade':
        output = get_cascade_plot(proj, results, year=None, plot_type=plot_type)
    else:
        output = get_plots(proj, results, plot_options=plot_options)
    if saveresults:
        print('Saving project...')
        save_project(proj)    
    return output
    


##################################################################################
#%% Optimization functions and RPCs
##################################################################################


def py_to_js_optim(py_optim, project=None):
    js_optim = sw.json_sanitize_result(py_optim.json)
    for prog_name in js_optim['prog_spending']:
        prog_label = project.progset().programs[prog_name].label
        this_prog = js_optim['prog_spending'][prog_name]
        this_prog.append(prog_label)
        js_optim['prog_spending'][prog_name] = {'min':this_prog[0], 'max':this_prog[1], 'label':prog_label}
    return js_optim
    

@register_RPC(validation_type='nonanonymous user')    
def get_optim_info(project_id):
    print('Getting optimization info...')
    proj = load_project(project_id, raise_exception=True)
    optim_summaries = []
    for py_optim in proj.optims.values():
        js_optim = py_to_js_optim(py_optim, project=proj)
        optim_summaries.append(js_optim)
    print('JavaScript optimization info:')
    print(optim_summaries)
    return optim_summaries


@register_RPC(validation_type='nonanonymous user')    
def get_default_optim(project_id):
    print('Getting default optimization...')
    proj = load_project(project_id, raise_exception=True)
    py_optim = proj.demo_optimization()
    js_optim = py_to_js_optim(py_optim, project=proj)
    print('Created default optimization:')
    print(js_optim)
    return js_optim


def to_number(raw):
    ''' Convert something to a number. WARNING, I'm sure this already exists!! '''
    try:
        output = float(raw)
    except Exception as E:
        if raw is None:
            output = None
        else:
            raise E
    return output


@register_RPC(validation_type='nonanonymous user')    
def set_optim_info(project_id, optim_summaries):
    print('Setting optimization info...')
    proj = load_project(project_id, raise_exception=True)
    for j,js_optim in enumerate(optim_summaries):
        print('Setting optimization %s of %s...' % (j+1, len(optim_summaries)))
        json = js_optim
        for key in ['start_year', 'end_year', 'budget_factor', 'maxtime']:
            json[key] = to_number(json[key]) # Convert to a number
        for subkey in json['objective_weights'].keys():
            json['objective_weights'][subkey] = to_number(json['objective_weights'][subkey])
        for subkey in json['prog_spending'].keys():
            this = json['prog_spending'][subkey]
            json['prog_spending'][subkey] = (to_number(this['min']), to_number(this['max']))
        print('Python optimization info for optimization %s:' % (j+1))
        print(json)
        proj.make_optimization(json=json)
    print('Saving project...')
    save_project(proj)   
    return None


# Deprecated, see equivalent in apptasks.py
#@register_RPC(validation_type='nonanonymous user')    
#def run_optimization(project_id, optim_name):
#    print('Running optimization...')
#    proj = load_project(project_id, raise_exception=True)
#    results = proj.run_optimization(optim_name)
#    output = get_plots(proj, results) # outputs=['alive','ddis']
#    print('Saving project...')
#    save_project(proj)    
#    return output