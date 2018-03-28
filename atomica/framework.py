# -*- coding: utf-8 -*-
"""
Atomica project-framework file.
Contains all information describing the context of a project.
This includes a description of the Markov chain network underlying project dynamics.
"""
from atomica.system import SystemSettings as SS, applyToAllMethods, logUsage
from atomica.structure_settings import FrameworkSettings as FS, DatabookSettings as DS, TimeDependentValuesEntry
from atomica.structure import CoreProjectStructure
from atomica.workbook_import import readWorkbook
from atomica._version import __version__
from sciris.core import odict, makefilepath, today, gitinfo, objrepr, getdate, dcp, uuid, saveobj


@applyToAllMethods(logUsage)
class ProjectFramework(CoreProjectStructure):
    """ The object that defines the transition-network structure of models generated by a project. """
    
    def __init__(self, name="SIR", frameworkfilename=None, **kwargs):
        """ Initialize the framework. """
        super(ProjectFramework, self).__init__(structure_key = SS.STRUCTURE_KEY_FRAMEWORK, **kwargs) #TODO: figure out & remove replication from below

        ## Define metadata
        self.name = name
        self.filename = None # Never yet saved to file
        self.uid = uuid()
        self.created = today()
        self.modified = today()
        self.version = __version__
        self.gitinfo = gitinfo()
        self.frameworkfileloaddate = 'Framework file never loaded'

        ## Load framework file if provided
        if frameworkfilename:
            self.readFrameworkfile(frameworkfilename=frameworkfilename)

        return None


    def __repr__(self):
        ''' Print out useful information when called '''
        output = objrepr(self)
        output += '    Framework name: %s\n'    % self.name
        output += '\n'
        output += '   Atomica version: %s\n'    % self.version
        output += '      Date created: %s\n'    % getdate(self.created)
        output += '     Date modified: %s\n'    % getdate(self.modified)
        output += '  Datasheet loaded: %s\n'    % getdate(self.frameworkfileloaddate)
        output += '        Git branch: %s\n'    % self.gitinfo['branch']
        output += '          Git hash: %s\n'    % self.gitinfo['hash']
        output += '               UID: %s\n'    % self.uid
        output += '============================================================\n'
        return output
    

    def completeSpecs(self):
        """
        A method for completing specifications that is called at the end of a file import.
        This delay is because some specifications rely on other definitions and values existing in the specs dictionary.
        """
        # Construct specifications for constructing a databook beyond the information contained in default databook settings.
        self.specs[FS.KEY_DATAPAGE] = odict()
        self.createDatabookSpecs()

    def createDatabookSpecs(self):
        """
        Generate framework-dependent databook settings that are a fusion of static databook settings and dynamic framework specifics.
        These are the ones that databook construction processes use when deciding layout.
        """
        # Copy default page keys over.
        for page_key in DS.PAGE_KEYS:
            self.specs[FS.KEY_DATAPAGE][page_key] = odict()
            
            # Do a scan over page tables in default databook settings.
            # If any are templated, i.e. are duplicated per instance of an item type, all tables must be copied over and duplicated where necessary.
            copy_over = False
            for table in DS.PAGE_SPECS[page_key]["tables"]:
                if isinstance(table, TimeDependentValuesEntry):
                    copy_over = True
                    break

            if copy_over:
                for page_attribute in DS.PAGE_SPECS[page_key]:
                    if not page_attribute == "tables": self.specs[FS.KEY_DATAPAGE][page_key][page_attribute] = DS.PAGE_SPECS[page_key][page_attribute]
                    else:
                        self.specs[FS.KEY_DATAPAGE][page_key]["tables"] = []
                        for table in DS.PAGE_SPECS[page_key]["tables"]:
                            if isinstance(table, TimeDependentValuesEntry):
                                item_type = table.item_type
                                for item_key in self.specs[item_type]:
                                    instantiated_table = dcp(table)
                                    instantiated_table.item_key = item_key
                                    self.specs[FS.KEY_DATAPAGE][page_key]["tables"].append(instantiated_table)
                            else:
                                self.specs[FS.KEY_DATAPAGE][page_key]["tables"].append(table)

            else: self.specs[FS.KEY_DATAPAGE][page_key]["refer_to_default"] = True
            
    
# TODO: Setup all following methods in Project, with maybe save as an exception.        
    def writeFrameworkfile(self, filename, data=None, instructions=None):
        ''' Export a framework file from framework'''        
        # TODO: modify writeWorkbook so it can write framework specs to an excel file???
        pass


    def readFrameworkfile(self, frameworkfilename=None):
        ''' Export a databook from framework '''        
        frameworkfileout = readWorkbook(workbook_path=frameworkfilename, framework=self, workbook_type=SS.STRUCTURE_KEY_FRAMEWORK)
        self.frameworkfileout = frameworkfileout # readWorkbook returns an odict of information about the workbook it just read. For framework files, this is blank at the moment. Think about what could go here & how it could be stored.
        self.frameworkfileloaddate = today()
        self.modified = today()
        
        return None


    def makemodel(self):
        '''Generate the model that goes with the framework'''
        pass


    def save(self, filename=None, folder=None, verbose=2):
        ''' Save the current project, by default using its name, and without results '''
        fullpath = makefilepath(filename=filename, folder=folder, ext='frw', sanitize=True)
        self.filename = fullpath # Store file path
        saveobj(fullpath, self, verbose=verbose)
        return fullpath


        