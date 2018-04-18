# -*- coding: utf-8 -*-
"""
Atomica project-framework file.
Contains all information describing the context of a project.
This includes a description of the Markov chain network underlying project dynamics.
"""
from atomica.system import SystemSettings as SS, applyToAllMethods, logUsage, logger, AtomicaException
from atomica.structure_settings import FrameworkSettings as FS, DatabookSettings as DS, TableTemplate
from atomica.structure import CoreProjectStructure
from atomica.workbook_import import readWorkbook
from atomica.parser_function import FunctionParser
from atomica._version import __version__
from sciris.core import odict, makefilepath, today, gitinfo, objrepr, getdate, dcp, uuid, saveobj


@applyToAllMethods(logUsage)
class ProjectFramework(CoreProjectStructure):
    """ The object that defines the transition-network structure of models generated by a project. """
    
    def __init__(self, name="SIR", frameworkfilename=None, **kwargs):
        """ Initialize the framework. """
        super(ProjectFramework, self).__init__(structure_key = SS.STRUCTURE_KEY_FRAMEWORK, **kwargs) #TODO: figure out & remove replication from below

        # One copy of a function parser stored for performance sake.
        self.parser = FunctionParser()
        
        # Set up a filter for quick referencing items of a certain group.
        self.filter = {FS.TERM_FUNCTION + FS.KEY_PARAMETER : []}

        ## Define metadata
#        self.name = name   #Already in ProjectStructure.
        self.filename = None # Never yet saved to file
#        self.frameworkfileloaddate = 'Framework file never loaded'

        ## Load framework file if provided
        if frameworkfilename:
            self.readFrameworkfile(frameworkfilename=frameworkfilename)

        return None

    def completeSpecs(self, **kwargs):
        """
        A method for completing specifications that is called at the end of a file import.
        This delay is because some specifications rely on other definitions and values existing in the specs dictionary.
        """
        self.parseFunctionSpecs()
        self.createDatabookSpecs()  # Construct specifications for constructing a databook beyond info contained in default databook settings.
        self.validateSpecs()

    def parseFunctionSpecs(self):
        """ If any parameters are associated with functions, convert them into lists of tokens. """
        self.filter[FS.TERM_FUNCTION + FS.KEY_PARAMETER] = []
        for item_key in self.specs[FS.KEY_PARAMETER]:
            if not self.getSpecValue(item_key, FS.TERM_FUNCTION) is None:
                self.filter[FS.TERM_FUNCTION + FS.KEY_PARAMETER].append(item_key)
                function_stack, dependencies = self.parser.produceStack(self.getSpecValue(item_key, FS.TERM_FUNCTION).replace(" ",""))
                self.setSpecValue(item_key, attribute = FS.TERM_FUNCTION, value = function_stack)
                self.setSpecValue(item_key, attribute = "dependencies", value = dependencies)

    def createDatabookSpecs(self):
        """
        Generates framework-dependent databook settings that are a fusion of static databook settings and dynamic framework specifics.
        These are the ones that databook construction processes use when deciding layout.
        """
        # Copy default page keys over.
        for page_key in DS.PAGE_KEYS:
            self.createItem(item_name = page_key, item_type = FS.KEY_DATAPAGE)
            
            # Do a scan over page tables in default databook settings.
            # If any are templated, i.e. are duplicated per instance of an item type, all tables must be copied over and duplicated where necessary.
            copy_over = False
            for table in DS.PAGE_SPECS[page_key]["tables"]:
                if isinstance(table, TableTemplate):
                    copy_over = True
                    break

            if copy_over:
                for page_attribute in DS.PAGE_SPECS[page_key]:
                    if not page_attribute == "tables": self.setSpecValue(term = page_key, attribute = page_attribute, value = DS.PAGE_SPECS[page_key][page_attribute])
                    else:
                        for table in DS.PAGE_SPECS[page_key]["tables"]:
                            if isinstance(table, TableTemplate):
                                item_type = table.item_type
                                for item_key in self.specs[item_type]:
                                    # Do not create tables for items that are marked not to be shown in a datapage.
                                    # Warn if they should be.
                                    if ("datapage_order" in self.getSpec(item_key) and self.getSpecValue(item_key,"datapage_order") == -1):
                                        if ("setup_weight" in self.getSpec(item_key) and not self.getSpecValue(item_key,"setup_weight") == 0.0):
                                            logger.warn("Item '{0}' of type '{1}' is associated with a non-zero setup weight of '{2}' "
                                                        "but a databook ordering of '-1'. Users will not be able to supply "
                                                        "important values.".format(item_key, item_type, self.getSpecValue(item_key,"setup_weight")))
                                    # Otherwise create the tables.
                                    else:
                                        instantiated_table = dcp(table)
                                        instantiated_table.item_key = item_key
                                        self.appendSpecValue(term = page_key, attribute = "tables", value = instantiated_table)
                            else:
                                self.appendSpecValue(term = page_key, attribute = "tables", value = table)

            else: self.setSpecValue(term = page_key, attribute = "refer_to_default", value = True)
            
    def validateSpecs(self):
        """ Check that framework specifications make sense. """
        for item_key in self.specs[FS.KEY_COMPARTMENT]:
            special_comp_tags = [self.getSpecValue(item_key,"is_source"),
                                 self.getSpecValue(item_key,"is_sink"),
                                 self.getSpecValue(item_key,"is_junction")]
            if special_comp_tags.count(True) > 1: 
                raise AtomicaException("Compartment '{0}' can only be a source, sink or junction, not a combination of two or more.".format(item_key))
            if special_comp_tags[0:2].count(True) > 0:
                if not self.getSpecValue(item_key,"setup_weight") == 0.0:
                    raise AtomicaException("Compartment '{0}' cannot be a source or sink and also have a nonzero setup weight. "
                                           "Check that setup weight was explicitly set to `0`.".format(item_key))
                if not self.getSpecValue(item_key,"datapage_order") == -1:
                    raise AtomicaException("Compartment '{0}' cannot be a source or sink and not have a '-1' databook ordering. "
                                           "It must be explicitly excluded from querying its population size in a databook.".format(item_key))
        
            
    
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


#    def makemodel(self):
#        '''Generate the model that goes with the framework'''
#        pass


    def save(self, filename=None, folder=None, verbose=2):
        ''' Save the current project, by default using its name, and without results '''
        fullpath = makefilepath(filename=filename, folder=folder, ext='frw', sanitize=True)
        self.filename = fullpath # Store file path
        saveobj(fullpath, self, verbose=verbose)
        return fullpath


        