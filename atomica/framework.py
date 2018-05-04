# -*- coding: utf-8 -*-
"""
Atomica project-framework file.
Contains all information describing the context of a project.
This includes a description of the Markov chain network underlying project dynamics.
"""
from atomica.system import SystemSettings as SS, apply_to_all_methods, log_usage, logger, AtomicaException
from atomica.structure_settings import FrameworkSettings as FS, DataSettings as DS, TableTemplate
from atomica.structure import CoreProjectStructure, get_quantity_type_list
from atomica.workbook_export import makeInstructions, writeWorkbook
from atomica.workbook_import import readWorkbook
from atomica.parser_function import FunctionParser
from sciris.core import makefilepath, today, dcp, saveobj, loadobj


@apply_to_all_methods(log_usage)
class ProjectFramework(CoreProjectStructure):
    """ The object that defines the transition-network structure of models generated by a project. """
    
    def __init__(self, name="SIR", filepath=None, **kwargs):
        """ Initialize the framework. """
        super(ProjectFramework, self).__init__(structure_key = SS.STRUCTURE_KEY_FRAMEWORK, **kwargs) #TODO: figure out & remove replication from below

        # One copy of a function parser stored for performance sake.
        self.parser = FunctionParser()
        
        # Set up a filter for quick referencing items of a certain group.
        self.filter = {FS.TERM_FUNCTION + FS.KEY_PARAMETER : []}

        ## Define metadata
#        self.name = name   #Already in ProjectStructure.
#        self.filename = None # Never yet saved to file
#        self.frameworkfileloaddate = 'Framework file never loaded'

        ## Load framework file if provided
        if filepath:
            self.readFromFile(filepath=filepath)

        return None

    def complete_specs(self, **kwargs):
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
            if not self.get_spec_value(item_key, FS.TERM_FUNCTION) is None:
                self.filter[FS.TERM_FUNCTION + FS.KEY_PARAMETER].append(item_key)
                function_stack, dependencies = self.parser.produceStack(self.get_spec_value(item_key, FS.TERM_FUNCTION).replace(" ", ""))
                self.set_spec_value(item_key, attribute = FS.TERM_FUNCTION, value = function_stack)
                self.set_spec_value(item_key, attribute ="dependencies", value = dependencies)

    def createDatabookSpecs(self):
        """
        Generates framework-dependent databook settings that are a fusion of static databook settings and dynamic framework specifics.
        These are the ones that databook construction processes use when deciding layout.
        """
        # Copy page keys from databook settings into framework datapage objects.
        for page_key in reversed(DS.PAGE_KEYS):
            position = 0
            if page_key in [DS.KEY_CHARACTERISTIC, DS.KEY_PARAMETER]: position = None
            self.create_item(item_name = page_key, item_type = FS.KEY_DATAPAGE, position = position)
        
            # Do a scan over page tables in default databook settings.
            # If any are templated, i.e. are duplicated per instance of an item type, all tables must be copied over and duplicated where necessary.
        for page_key in DS.PAGE_KEYS:
            copy_over = False
            for table in DS.PAGE_SPECS[page_key]["tables"]:
                if isinstance(table, TableTemplate):
                    copy_over = True
                    break

            if copy_over:
                for page_attribute in DS.PAGE_SPECS[page_key]:
                    if not page_attribute == "tables": self.set_spec_value(term = page_key, attribute = page_attribute, value = DS.PAGE_SPECS[page_key][page_attribute])
                    else:
                        for table in DS.PAGE_SPECS[page_key]["tables"]:
                            if isinstance(table, TableTemplate):
                                item_type = table.item_type
                                for item_key in self.specs[item_type]:
                                    # Do not create tables for items that are marked not to be shown in a datapage.
                                    # Warn if they should be.
                                    if ("datapage_order" in self.get_spec(item_key) and self.get_spec_value(item_key, "datapage_order") == -1):
                                        if ("setup_weight" in self.get_spec(item_key) and not self.get_spec_value(item_key, "setup_weight") == 0.0):
                                            logger.warning("Item '{0}' of type '{1}' is associated with a non-zero setup weight of '{2}' "
                                                           "but a databook ordering of '-1'. Users will not be able to supply "
                                                           "important values.".format(item_key, item_type, self.get_spec_value(item_key, "setup_weight")))
                                    # Otherwise create the tables.
                                    else:
                                        actual_page_key = page_key
                                        if FS.KEY_DATAPAGE in self.specs[item_type][item_key] and not self.specs[item_type][item_key][FS.KEY_DATAPAGE] is None:
                                            actual_page_key = self.specs[item_type][item_key][FS.KEY_DATAPAGE]
                                        instantiated_table = dcp(table)
                                        instantiated_table.item_key = item_key
                                        self.append_spec_value(term = actual_page_key, attribute ="tables", value = instantiated_table)
                            else:
                                self.append_spec_value(term = page_key, attribute ="tables", value = table)
            # Keep framework specifications minimal by referring to settings when possible.
            # TODO: Reconsider. Currently does not save much space as attribute dictionary is still constructed by self.create_item().
            else: self.set_spec_value(term = page_key, attribute ="refer_to_settings", value = True)
            
    def validateSpecs(self):
        """ Check that framework specifications make sense. """
        for item_key in self.specs[FS.KEY_COMPARTMENT]:
            special_comp_tags = [self.get_spec_value(item_key, "is_source"),
                                 self.get_spec_value(item_key, "is_sink"),
                                 self.get_spec_value(item_key, "is_junction")]
            if special_comp_tags.count(True) > 1: 
                raise AtomicaException("Compartment '{0}' can only be a source, sink or junction, not a combination of two or more.".format(item_key))
            if special_comp_tags[0:2].count(True) > 0:
                if not self.get_spec_value(item_key, "setup_weight") == 0.0:
                    raise AtomicaException("Compartment '{0}' cannot be a source or sink and also have a nonzero setup weight. "
                                           "Check that setup weight was explicitly set to '0'.".format(item_key))
                if not self.get_spec_value(item_key, "datapage_order") == -1:
                    raise AtomicaException("Compartment '{0}' cannot be a source or sink and not have a '-1' databook ordering. "
                                           "It must be explicitly excluded from querying its population size in a databook.".format(item_key))
        for item_key in self.specs[FS.KEY_PARAMETER]:
            # Validate transition-matrix and parameter matching.
            if self.get_spec_value(item_key, "label") is None:
                raise AtomicaException("Parameter '{0}' has no label. This is likely because it was used to mark a link in a transition matrix "
                                       "but was left undefined on the parameters page of a framework file.".format(item_key))
            # Make sure functional parameters have a specified format.
            links = self.get_spec_value(item_key, "links")
            if len(links) > 0:
                if (not self.get_spec_value(item_key, FS.TERM_FUNCTION) is None and
                    not self.get_spec_value(item_key, "format") in get_quantity_type_list(include_absolute = True, include_relative = True, include_special = True)):
                    raise AtomicaException("Parameter '{0}' is associated with transitions and is expressed as a custom function of other parameters. "
                                           "A format must be specified for it in a framework file.".format(item_key))
            for link in links:
                # Validate parameter-related transitions with source/sink compartments.
                if self.get_spec_value(link[0], "is_sink"):
                    raise AtomicaException("Parameter '{0}' cannot be associated with a transition from compartment '{1}' to '{2}'. "
                                           "Compartment '{1}' is strictly a sink compartment.".format(item_key,link[0],link[-1]))
                if self.get_spec_value(link[-1], "is_source"):
                    raise AtomicaException("Parameter '{0}' cannot be associated with a transition from compartment '{1}' to '{2}'. "
                                           "Compartment '{2}' is strictly a source compartment.".format(item_key,link[0],link[-1]))
                if self.get_spec_value(link[0], "is_source"):
                    if self.get_spec_value(link[-1], "is_sink"):
                        raise AtomicaException("Parameter '{0}' should not be associated with a transition from compartment '{1}' to '{2}'. "
                                               "This is a pointless flow from source to sink compartment.".format(item_key,link[0],link[-1]))
                    if len(links) > 1:
                        raise AtomicaException("Parameter '{0}' is associated with a transition from source compartment '{1}' to '{2}'. "
                                               "This restricts any other transitions being marked '{0}' due to flow disaggregation ambiguity.".format(item_key,link[0],link[-1]))
                    if not self.get_spec_value(item_key, "format") in get_quantity_type_list(include_absolute = True):
                        raise AtomicaException("Parameter '{0}' is associated with a transition from source compartment '{1}' to '{2}'. "
                                               "The format of the parameter must thus be specified as: '{3}'".format(item_key, link[0], link[-1],
                                                                                                                     "' or '".join(get_quantity_type_list(include_absolute = True))))
                # Validate parameter-related transitions with junction compartments.
                if self.get_spec_value(link[0], "is_junction"):
                    if len(links) > 1:
                        # TODO: Avoid repetitive exception code. Encapsulate all exceptions.
                        raise AtomicaException("Parameter '{0}' is associated with a transition from junction compartment '{1}' to '{2}'. "
                                               "This restricts any other transitions being marked '{0}' due to flow disaggregation ambiguity.".format(item_key,link[0],link[-1]))
                    if not self.get_spec_value(item_key, "format") == FS.QUANTITY_TYPE_PROPORTION:
                        raise AtomicaException("Parameter '{0}' is associated with a transition from junction compartment '{1}' to '{2}'. "
                                               "The format of the parameter must thus be specified as: '{3}'".format(item_key,link[0],link[-1],FS.QUANTITY_TYPE_PROPORTION))
                if self.get_spec_value(item_key, "format") == FS.QUANTITY_TYPE_PROPORTION:
                    if not self.get_spec_value(link[0], "is_junction"):
                        raise AtomicaException("Parameter '{0}' is associated with a transition from non-junction compartment '{1}' to '{2}'. "
                                               "It is also incorrectly given a 'proportion' format which can only describe transitions from junctions.".format(item_key,link[0],link[-1]))
                    
            

    @classmethod
    def createTemplate(cls, path, num_comps=None, num_characs=None, num_pars=None, num_datapages=None):
        """ Convenience class method for template creation in the absence of an instance. """
        framework_instructions, _ = makeInstructions(workbook_type=SS.STRUCTURE_KEY_FRAMEWORK)
        if not num_comps is None:       framework_instructions.updateNumberOfItems(FS.KEY_COMPARTMENT, num_comps)           # Set the number of compartments.
        if not num_characs is None:     framework_instructions.updateNumberOfItems(FS.KEY_CHARACTERISTIC, num_characs)      # Set the number of characteristics.
        if not num_pars is None:        framework_instructions.updateNumberOfItems(FS.KEY_PARAMETER, num_pars)              # Set the number of parameters.
        if not num_datapages is None:   framework_instructions.updateNumberOfItems(FS.KEY_DATAPAGE, num_datapages)          # Set the number of custom databook pages.
    
        writeWorkbook(workbook_path=path, instructions=framework_instructions, workbook_type=SS.STRUCTURE_KEY_FRAMEWORK)
            
        
    def writeToFile(self, filename, data=None, instructions=None):
        """ Export a framework to file. """       
        # TODO: modify writeWorkbook so it can write framework specs to an excel file???
        pass

    def readFromFile(self, filepath=None):
        """ Import a framework from file. """      
        frameworkfileout = readWorkbook(workbook_path=filepath, framework=self, workbook_type=SS.STRUCTURE_KEY_FRAMEWORK)
        self.frameworkfileout = frameworkfileout # readWorkbook returns an odict of information about the workbook it just read. For framework files, this is blank at the moment. Think about what could go here & how it could be stored.
        self.workbook_load_date = today()
        self.modified = today()        