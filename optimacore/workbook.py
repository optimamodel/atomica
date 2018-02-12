from optimacore.system import SystemSettings as SS
from optimacore.framework_settings import FrameworkSettings as FS
from optimacore.framework_settings import DatabookSettings as DS
from optimacore.excel import ExcelSettings as ES

from optimacore.system import logger, OptimaException, accepts, prepareFilePath, displayName
from optimacore.excel import createStandardExcelFormats, createDefaultFormatVariables, extractHeaderColumnsMapping, extractExcelSheetValue
from optimacore.framework_settings import DetailColumns, LabelType, NameType, SwitchType, AttributeReference, SuperReference, ExtraSelfReference
from optimacore.framework import ProjectFramework

import os
from collections import OrderedDict
from copy import deepcopy as dcp
from six import moves as sm
import xlsxwriter as xw
import xlrd

class WorkbookTypeException(OptimaException):
    def __init__(self, workbook_type, **kwargs):
        available_workbook_types = [SS.WORKBOOK_KEY_FRAMEWORK, SS.WORKBOOK_KEY_DATA]
        message = ("Unable to operate read and write processes for a workbook of type '{0}'. "
                   "Available options are: '{1}'".format(workbook_type, "' or '".join(available_workbook_types)))
        return super().__init__(message, **kwargs)

class WorkbookRequirementException(OptimaException):
    def __init__(self, workbook_type, requirement_type, **kwargs):
        available_workbook_types = [SS.WORKBOOK_KEY_FRAMEWORK, SS.WORKBOOK_KEY_DATA]
        message = ("{0} construction cannot proceed without a '{1}' being provided. Abandoning workbook construction.".format(displayName(workbook_type, as_title = True), requirement_type))
        return super().__init__(message, **kwargs)

class KeyUniquenessException(OptimaException):
    def __init__(self, key, dict_type, **kwargs):
        if key is None: message = ("Key uniqueness failure. A key is used more than once in '{0}'.".format(dict_type))
        else: message = ("Key uniqueness failure. Key '{0}' is used more than once in '{1}'.".format(key, dict_type))
        return super().__init__(message, **kwargs)

class InvalidReferenceException(OptimaException):
    def __init__(self, item_type, attribute, ref_item_type, ref_attribute, **kwargs):
        message = ("Workbook construction failed when item '{0}', attribute '{1}', attempted to reference nonexistent values, specifically item '{2}', attribute '{3}'. "
                   "It is possible the referenced attribute values are erroneously scheduled to be created later.".format(item_type, attribute, ref_item_type, ref_attribute))
        return super().__init__(message, **kwargs)

class WorkbookInstructions(object):
    """ An object that stores instructions for how many items should be created during workbook construction. """
    
    def __init__(self, workbook_type = None):
        """ Initialize instructions that detail how to construct a workbook. """
        # Every relevant item must be included in a dictionary that lists how many should be created.
        self.num_items = OrderedDict()
        if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK: item_type_specs = FS.ITEM_TYPE_SPECS
        else: raise WorkbookTypeException(workbook_type)
        for item_type in item_type_specs:
            self.num_items[item_type] = item_type_specs[item_type]["default_amount"]
                          
    @accepts(str,int)
    def updateNumberOfItems(self, item_type, number):
        """ Overwrite the number of items that will be constructed for the template workbook. """
        try: self.num_items[item_type] = number
        except:
            logger.error("An attempted update of workbook instructions to produce '{0}' instances of item type '{1}' failed.".format(number, item_type))
            raise

def getWorkbookPageKeys(framework = None, workbook_type = None):
    if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK:
        page_keys = FS.PAGE_KEYS
    elif workbook_type == SS.WORKBOOK_KEY_DATA:
        if framework is None:
            raise WorkbookRequirementException(workbook_type = SS.WORKBOOK_KEY_DATA, requirement_type = "ProjectFramework")
        page_keys = framework.specs[FS.KEY_DATAPAGE].keys()
    else:
        raise WorkbookTypeException(workbook_type)
    return page_keys

def writeHeaders(worksheet, item_type, start_row, start_col, framework = None, data = None, instructions = None, workbook_type = None, formats = None, format_variables = None):
    if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK: item_type_spec = FS.ITEM_TYPE_SPECS[item_type]
    #table_types = FS.PAGE_TABLE_TYPES[page_key]
#elif workbook_type == SS.WORKBOOK_KEY_DATA:
    else: raise WorkbookTypeException(workbook_type)

    if formats is None: raise OptimaException("Excel formats have not been passed to workbook table construction.")
    if format_variables is None: format_variables = createDefaultFormatVariables()
    orig_format_variables = dcp(format_variables)
    format_variables = dcp(orig_format_variables)
    revert_format_variables = False

    row, col, header_column_map = start_row, start_col, dict()
    for attribute in item_type_spec["attributes"]:
        attribute_spec = item_type_spec["attributes"][attribute]
        if "ref_item_type" in attribute_spec:
            _, col, sub_map = writeHeaders(worksheet = worksheet, item_type = attribute_spec["ref_item_type"],
                                           start_row = row, start_col = col,
                                           framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                                           formats = formats, format_variables = format_variables)
            len_map = len(header_column_map)
            len_sub_map = len(sub_map)
            header_column_map.update(sub_map)
            if not len(header_column_map) == len_map + len_sub_map: raise KeyUniquenessException(None, "header-column map")
        else:
            for format_variable_key in format_variables:
                if format_variable_key in attribute_spec:
                    revert_format_variables = True
                    format_variables[format_variable_key] = attribute_spec[format_variable_key]
            header = attribute_spec["header"]
            if header in header_column_map: raise KeyUniquenessException(header, "header-column map")
            header_column_map[header] = col
            worksheet.write(row, col, header, formats["center_bold"])
            if "comment" in attribute_spec:
                header_comment = attribute_spec["comment"]
                worksheet.write_comment(row, col, header_comment, 
                                        {"x_scale": format_variables[ES.KEY_COMMENT_XSCALE], 
                                            "y_scale": format_variables[ES.KEY_COMMENT_YSCALE]})
            worksheet.set_column(col, col, format_variables[ES.KEY_COLUMN_WIDTH])
            if revert_format_variables:
                format_variables = dcp(orig_format_variables)
                revert_format_variables = False
            col += 1
    row += 1
    next_row, next_col = row, col
    return next_row, next_col, header_column_map

def writeContents(worksheet, item_type, start_row, header_column_map, framework = None, data = None, instructions = None, workbook_type = None,
                  formats = None, temp_storage = None):
    if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK: 
        item_type_specs = FS.ITEM_TYPE_SPECS
        item_type_spec = FS.ITEM_TYPE_SPECS[item_type]
        if framework is None:
            if instructions is None: instructions = WorkbookInstructions(workbook_type = workbook_type)
        else:
            print('WHOOPS')
    #table_types = FS.PAGE_TABLE_TYPES[page_key]
#elif workbook_type == SS.WORKBOOK_KEY_DATA:
    else: raise WorkbookTypeException(workbook_type)

    if formats is None: raise OptimaException("Excel formats have not been passed to workbook table construction.")
    cell_format = formats["center"]

    if temp_storage is None: temp_storage = dict()

    row, new_row = start_row, start_row
    for item_number in sm.range(instructions.num_items[item_type]):
        for attribute in item_type_spec["attributes"]:
            attribute_spec = item_type_spec["attributes"][attribute]
            if "ref_item_type" in attribute_spec:
                sub_row = writeContents(worksheet = worksheet, item_type = attribute_spec["ref_item_type"],
                                           start_row = row, header_column_map = header_column_map,
                                           framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                                           formats = formats, temp_storage = temp_storage)
                new_row = max(new_row, sub_row)
            else:
                col = header_column_map[attribute_spec["header"]]
                rc = xw.utility.xl_rowcol_to_cell(row, col)

                content = ""
                space = ""
                sep = ""
                validation_source = None

                reference_type = None
                content_type = attribute_spec["content_type"]
                if isinstance(content_type, AttributeReference): reference_type = dcp(content_type)
                # Content types that are references to superitem attributes copy their content type.
                if isinstance(content_type, SuperReference):
                    content_type = item_type_specs[reference_type.other_item_type]["attributes"][reference_type.other_attribute]["content_type"]
                if isinstance(content_type, LabelType) or isinstance(content_type, NameType):
                    content = str(item_number)     # The default is the number of this item.
                    if isinstance(content_type, LabelType):
                        space = SS.DEFAULT_SPACE_LABEL
                        sep = SS.DEFAULT_SEPARATOR_LABEL
                    else:
                        space = SS.DEFAULT_SPACE_NAME
                        sep = SS.DEFAULT_SEPARATOR_NAME
                    if "prefix" in attribute_spec:
                        content = attribute_spec["prefix"] + space + content
                elif isinstance(content_type, SwitchType):
                    validation_source = [SS.DEFAULT_SYMBOL_NO, SS.DEFAULT_SYMBOL_YES]
                    if content_type.default_on: validation_source.reverse()
                    content = validation_source[0]
                content_backup = content

                if not reference_type is None:
                    # 'Super' references link subitem attributes to corresponding superitem attributes.
                    # Because subitem displays are created instantly after superitems, the superitem referenced is the last one stored.
                    list_id = item_number
                    if isinstance(reference_type, SuperReference): list_id = -1
                    try: stored_refs = temp_storage[reference_type.other_item_type][reference_type.other_attribute]
                    except: raise InvalidReferenceException(item_type = item_type, attribute = attribute, ref_item_type = reference_type.item_type, ref_attribute = reference_type.attribute)
                    # For one-to-one referencing, do not create content for tables that extent beyond the length of the referenced table.
                    if len(stored_refs["list_content"]) > list_id:
                        content_page = ""
                        if not stored_refs["page_label"] == worksheet.name: content_page = "'{0}'!".format(stored_refs["page_label"])
                        ref_content = "={0}{1}".format(content_page, stored_refs["list_cell"][list_id])
                        ref_content_backup = stored_refs["list_content_backup"][list_id]
                        if isinstance(reference_type, SuperReference):
                            content = "=CONCATENATE({0},\"{1}\")".format(ref_content.lstrip("="), sep + content)
                            content_backup = ref_content_backup + sep + content_backup
                        else:
                            content = ref_content
                            content_backup = ref_content_backup
                    # Append a self-reference to the content, which should be to an attribute of the same item a row ago.
                    if isinstance(reference_type, ExtraSelfReference) and reference_type.is_list is True and item_number > 0: 
                        list_id = item_number - 1
                        try: stored_refs = temp_storage[reference_type.own_item_type][reference_type.own_attribute]
                        except: raise InvalidReferenceException(item_type = item_type, attribute = attribute, ref_item_type = reference_type.own_item_type, ref_attribute = reference_type.own_attribute)
                        content_page = ""
                        if not stored_refs["page_label"] == worksheet.name: content_page = "'{0}'!".format(stored_refs["page_label"])
                        ref_content = "={0}{1}".format(content_page, stored_refs["list_cell"][list_id])
                        ref_content_backup = stored_refs["list_content_backup"][list_id]
                        if content == "":
                            content = ref_content
                            content_backup = ref_content_backup
                        else:
                            if content.startswith("="): content = content.lstrip("=")
                            else: content = "\"" + content + "\""
                            content = "=CONCATENATE({0},\"{1}\",{2})".format(content, ES.LIST_SEPARATOR, ref_content.lstrip("="))
                            content_backup = content_backup + ES.LIST_SEPARATOR + ref_content_backup


                # Store the contents of this attribute for referencing by other attributes if required.
                if "is_ref" in attribute_spec and attribute_spec["is_ref"] is True:
                    if not item_type in temp_storage: temp_storage[item_type] = {}
                    if not attribute in temp_storage[item_type]: temp_storage[item_type][attribute] = {"list_content":[],"list_content_backup":[],"list_cell":[]}
                    # Make sure the attribute does not already have stored values associated with it.
                    if not len(temp_storage[item_type][attribute]["list_content"]) > item_number:
                        temp_storage[item_type][attribute]["list_content"].append(content)
                        temp_storage[item_type][attribute]["list_content_backup"].append(content_backup)
                        temp_storage[item_type][attribute]["list_cell"].append(rc)
                        temp_storage[item_type][attribute]["page_label"] = worksheet.name

                if content.startswith("="):
                    worksheet.write_formula(rc, content, cell_format, content_backup)
                else:
                    worksheet.write(rc, content, cell_format)

                if not validation_source is None:
                    worksheet.data_validation(rc, {"validate": "list", "source": validation_source})
        row = max(new_row, row + 1)
    next_row = row
    return next_row

def writeDetailColumns(worksheet, core_item_type, start_row, start_col, framework = None, data = None, instructions = None, workbook_type = None, 
                       formats = None, format_variables = None, temp_storage = None):
    if temp_storage is None: temp_storage = dict()

    row, col = start_row, start_col
    row, _, header_column_map = writeHeaders(worksheet = worksheet, item_type = core_item_type, start_row = row, start_col = col,
                          framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                          formats = formats, format_variables = format_variables)
    row = writeContents(worksheet = worksheet, item_type = core_item_type, start_row = row, header_column_map = header_column_map,
                           framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                           formats = formats, temp_storage = temp_storage)
    next_row, next_col = row, col
    return next_row, next_col


def writeTable(worksheet, table, start_row, start_col, framework = None, data = None, instructions = None, workbook_type = None, 
               formats = None, format_variables = None, temp_storage = None):

    # Check workbook type. Gather relevant details.
    if workbook_type not in [SS.WORKBOOK_KEY_FRAMEWORK, SS.WORKBOOK_KEY_DATA]:
        raise WorkbookTypeException(workbook_type)

    if temp_storage is None: temp_storage = dict()

    if isinstance(table, DetailColumns):
        core_item_type = table.item_type
        row, col = writeDetailColumns(worksheet = worksheet, core_item_type = core_item_type, start_row = start_row, start_col = start_col,
                                      framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                                      formats = formats, format_variables = format_variables, temp_storage = temp_storage)
    
    next_row, next_col = row, col
    return next_row, next_col





def writeWorksheet(workbook, page_key, framework = None, data = None, instructions = None, workbook_type = None, 
                   formats = None, format_variables = None, temp_storage = None):

    # Check workbook type. Gather relevant details.
    if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK:
        page_spec = FS.PAGE_SPECS[page_key]
        #table_types = FS.PAGE_TABLE_TYPES[page_key]
    #elif workbook_type == SS.WORKBOOK_KEY_DATA:
    else:
        raise WorkbookTypeException(workbook_type)

    # Construct worksheet.
    page_name = page_spec["title"]
    logger.info("Creating page: {0}".format(page_name))
    worksheet = workbook.add_worksheet(page_name)

    # Propagate file-wide format variable values to page-wide format variable values.
    # Create the format variables if they were not passed in from a file-wide context.
    # Overwrite the file-wide defaults if page-based specifics are available in framework settings.
    if format_variables is None: format_variables = createDefaultFormatVariables()
    else: format_variables = dcp(format_variables)
    for format_variable_key in format_variables:
        if format_variable_key in page_spec:
            format_variables[format_variable_key] = page_spec[format_variable_key]
    
    # Generate standard formats if they do not exist and construct headers for the page.
    if formats is None: formats = createStandardExcelFormats(workbook)

    if temp_storage is None: temp_storage = dict()

    # Iteratively construct tables.
    row, col = 0, 0
    for table in page_spec["tables"]:
        row, col = writeTable(worksheet = worksheet, table = table, start_row = row, start_col = col,
                              framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                              formats = formats, format_variables = format_variables, temp_storage = temp_storage)

@accepts(str)
def writeWorkbook(workbook_path, framework = None, data = None, instructions = None, workbook_type = None):

    page_keys = getWorkbookPageKeys(framework = framework, workbook_type = workbook_type)

    logger.info("Constructing a {0}: {1}".format(displayName(workbook_type), workbook_path))

    # Construct workbook and related formats.
    prepareFilePath(workbook_path)
    workbook = xw.Workbook(workbook_path)
    formats = createStandardExcelFormats(workbook)
    format_variables = createDefaultFormatVariables()

    # Create a storage dictionary for values and formulae that may persist between sections.
    temp_storage = dict()

    # Iteratively construct worksheets.
    for page_key in page_keys:
        writeWorksheet(workbook = workbook, page_key = page_key, 
                       framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                       formats = formats, format_variables = format_variables, temp_storage = temp_storage)
    workbook.close()

    logger.info("{0} construction complete.".format(displayName(workbook_type, as_title = True)))


def readContents(worksheet, item_type, start_row, header_columns_map, stop_row = None, framework = None, data = None, workbook_type = None, structure = None):
    if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK: 
        item_type_specs = FS.ITEM_TYPE_SPECS
        item_type_spec = FS.ITEM_TYPE_SPECS[item_type]
        if item_type not in framework.specs: framework.specs[item_type] = OrderedDict()
        if structure is None: structure = framework.specs[item_type]
        #if framework is None:
        #    print('OOPS')
        #else:
        #    print('WHOOPS')
    #table_types = FS.PAGE_TABLE_TYPES[page_key]
#elif workbook_type == SS.WORKBOOK_KEY_DATA:
    else: raise WorkbookTypeException(workbook_type)

    row = start_row
    item_name = ""
    if stop_row is None: stop_row = worksheet.nrows
    while row < stop_row:
        name_col = header_columns_map[item_type_spec["attributes"]["name"]["header"]][0]    # Only the first column matters for a name.
        test_name = str(worksheet.cell_value(row, name_col))
        if not test_name == "": item_name = test_name
        if not item_name == "":
            if not item_name in structure: structure[item_name] = dict()
            for attribute in item_type_spec["attributes"]:
                if attribute == "name": continue
                attribute_spec = item_type_spec["attributes"][attribute]
                if "ref_item_type" in attribute_spec:
                    if attribute not in structure[item_name]: structure[item_name][attribute] = OrderedDict()
                    readContents(worksheet = worksheet, item_type = attribute_spec["ref_item_type"],
                                               start_row = row, header_columns_map = header_columns_map, stop_row = row + 1,
                                               framework = framework, data = data, workbook_type = workbook_type,
                                               structure = structure[item_name][attribute])
                else:
                    start_col, last_col = header_columns_map[attribute_spec["header"]]
                    content_type = attribute_spec["content_type"]
                    filters = []
                    if not content_type is None:
                        if content_type.is_list: filters.append(ES.FILTER_KEY_LIST)
                        if isinstance(content_type, SwitchType): 
                            if content_type.default_on: filters.append(ES.FILTER_KEY_BOOLEAN_NO)
                            else: filters.append(ES.FILTER_KEY_BOOLEAN_YES)
                    # Reading currently allows extended columns but not rows.
                    value = extractExcelSheetValue(worksheet, start_row = row, start_col = start_col, stop_col = last_col + 1, filters = filters)
                    if not value is None: structure[item_name][attribute] = value
            row += 1
    next_row = row
    return next_row

def readDetailColumns(worksheet, core_item_type, start_row, framework = None, data = None, workbook_type = None):

    row = start_row
    header_columns_map = extractHeaderColumnsMapping(worksheet, row = row)
    row += 1
    row = readContents(worksheet = worksheet, item_type = core_item_type, start_row = row, header_columns_map = header_columns_map,
                       framework = framework, data = data, workbook_type = workbook_type)
    next_row = row
    return next_row


def readTable(worksheet, table, start_row, start_col, framework = None, data = None, workbook_type = None):

    # Check workbook type. Gather relevant details.
    if workbook_type not in [SS.WORKBOOK_KEY_FRAMEWORK, SS.WORKBOOK_KEY_DATA]:
        raise WorkbookTypeException(workbook_type)

    row, col = start_row, start_col
    if isinstance(table, DetailColumns):
        core_item_type = table.item_type
        row = readDetailColumns(worksheet = worksheet, core_item_type = core_item_type, start_row = start_row,
                                     framework = framework, data = data, workbook_type = workbook_type)
    
    next_row, next_col = row, col
    return next_row, next_col

def readWorksheet(workbook, page_key, framework = None, data = None, workbook_type = None):

    # Check workbook type. Gather relevant details.
    if workbook_type == SS.WORKBOOK_KEY_FRAMEWORK:
        page_spec = FS.PAGE_SPECS[page_key]
        #table_types = FS.PAGE_TABLE_TYPES[page_key]
    #elif workbook_type == SS.WORKBOOK_KEY_DATA:
    else:
        raise WorkbookTypeException(workbook_type)

    try: 
        page_title = page_spec["title"]
        worksheet = workbook.sheet_by_name(page_title)
    except:
        logger.error("Workbook does not contain a required page titled '{0}'.".format(page_title))
        raise

    # Iteratively parse tables.
    row, col = 0, 0
    for table in page_spec["tables"]:
        row, col = readTable(worksheet = worksheet, table = table, start_row = row, start_col = col,
                             framework = framework, data = data, workbook_type = workbook_type)

@accepts(str)
def readWorkbook(workbook_path, framework = None, data = None, workbook_type = None):

    page_keys = getWorkbookPageKeys(framework = framework, workbook_type = workbook_type)

    workbook_path = os.path.abspath(workbook_path)
    try: workbook = xlrd.open_workbook(workbook_path)
    except:
        logger.error("Workbook was not found.")
        raise

    # Iteratively parse worksheets.
    for page_key in page_keys:
        readWorksheet(workbook = workbook, page_key = page_key, 
                      framework = framework, data = data, workbook_type = workbook_type)