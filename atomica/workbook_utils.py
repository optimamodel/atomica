from atomica.system import AtomicaException, displayName, SystemSettings as SS
from atomica.structure_settings import FrameworkSettings as FS, DatabookSettings as DS

class WorkbookTypeException(AtomicaException):
    def __init__(self, workbook_type, **kwargs):
        available_workbook_types = [SS.STRUCTURE_KEY_FRAMEWORK, SS.STRUCTURE_KEY_DATA]
        message = ("Unable to operate read and write processes for a workbook of type '{0}'. "
                   "Available options are: '{1}'".format(workbook_type, "' or '".join(available_workbook_types)))
        return super().__init__(message, **kwargs)

class WorkbookRequirementException(AtomicaException):
    def __init__(self, workbook_type, requirement_type, **kwargs):
        message = ("Select {0} IO operations cannot proceed without a '{1}' being provided. Abandoning workbook IO.".format(displayName(workbook_type), requirement_type))
        return super().__init__(message, **kwargs)

def getWorkbookReferences(framework = None, workbook_type = None, refer_to_default = False):
    ref_dict = dict()
    if workbook_type == SS.STRUCTURE_KEY_FRAMEWORK:
        ref_dict["page_keys"] = FS.PAGE_KEYS
        ref_dict["page_specs"] = FS.PAGE_SPECS
        ref_dict["item_type_specs"] = FS.ITEM_TYPE_SPECS
        ref_dict["item_specs"] = dict()
    elif workbook_type == SS.STRUCTURE_KEY_DATA:
        if framework is None:
            raise WorkbookRequirementException(workbook_type = SS.STRUCTURE_KEY_DATA, requirement_type = "ProjectFramework")
        if refer_to_default is True:
            ref_dict["page_keys"] = DS.PAGE_KEYS
            ref_dict["page_specs"] = DS.PAGE_SPECS
        else:
            ref_dict["page_keys"] = framework.specs[FS.KEY_DATAPAGE].keys()
            ref_dict["page_specs"] = framework.specs[FS.KEY_DATAPAGE]
        ref_dict["item_type_specs"] = DS.ITEM_TYPE_SPECS
        ref_dict["item_specs"] = framework.specs
    else:
        raise WorkbookTypeException(workbook_type)
    return ref_dict

def getWorkbookPageKeys(framework = None, workbook_type = None):
    ref_dict = getWorkbookReferences(framework = framework, workbook_type = workbook_type)
    return ref_dict["page_keys"]

def getWorkbookPageSpec(page_key, framework = None, workbook_type = None):
    ref_dict = getWorkbookReferences(framework = framework, workbook_type = workbook_type)
    if "refer_to_default" in ref_dict["page_specs"][page_key] and ref_dict["page_specs"][page_key]["refer_to_default"] is True:
        ref_dict = getWorkbookReferences(framework = framework, workbook_type = workbook_type, refer_to_default = True)
    return ref_dict["page_specs"][page_key]

def getWorkbookItemTypeSpecs(framework = None, workbook_type = None):
    ref_dict = getWorkbookReferences(framework = framework, workbook_type = workbook_type)
    return ref_dict["item_type_specs"]

def getWorkbookItemSpecs(framework = None, workbook_type = None):
    """
    Get instantiated item specifications to aid in the construction of workbook.
    Note that none exist during framework construction, while databook construction has all item instances available in the framework.
    """
    ref_dict = getWorkbookReferences(framework = framework, workbook_type = workbook_type)
    return ref_dict["item_specs"]