from atomica.ui import SystemSettings as SS
from atomica.ui import FrameworkSettings as FS
from atomica.ui import DatabookSettings as DS
from atomica.ui import ExcelSettings as ES

from atomica.ui import logger, OptimaException, accepts, prepareFilePath, displayName
from atomica.ui import createStandardExcelFormats, createDefaultFormatVariables, createValueEntryBlock
from atomica.ui import DetailColumns, ConnectionMatrix, TimeDependentValuesEntry, IDType, IDRefType, SwitchType
from atomica.ui import WorkbookTypeException, getWorkbookPageKeys, getWorkbookPageSpec, getWorkbookItemTypeSpecs, getWorkbookItemSpecs

from sciris.core import odict, dcp
import xlsxwriter as xw


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
        self.num_items = odict()
        if workbook_type == SS.STRUCTURE_KEY_FRAMEWORK: item_type_specs = FS.ITEM_TYPE_SPECS
        elif workbook_type == SS.STRUCTURE_KEY_DATA: item_type_specs = DS.ITEM_TYPE_SPECS
        else: raise WorkbookTypeException(workbook_type)
        for item_type in item_type_specs:
            if item_type_specs[item_type]["instruction_allowed"]:
                self.num_items[item_type] = item_type_specs[item_type]["default_amount"]
                          
    @accepts(str,int)
    def updateNumberOfItems(self, item_type, number):
        """ Overwrite the number of items that will be constructed for the template workbook. """
        try: self.num_items[item_type] = number
        except:
            logger.error("An attempted update of workbook instructions to produce '{0}' instances of item type '{1}' failed.".format(number, item_type))
            raise

def makeInstructions(framework=None, data=None, instructions=None, workbook_type=None):
    """
    Generates instructions that detail the number of items pertinent to workbook construction processes.
    If a ProjectFramework or ProjectData structure is available, this will be used in filling out a workbook rather than via instructions.
    In that case, this function will return a boolean tag indicating whether to use instructions or not.
    """
    use_instructions = True
    if instructions is None: instructions = WorkbookInstructions(workbook_type = workbook_type)
    if workbook_type == SS.STRUCTURE_KEY_FRAMEWORK:
        if not framework is None: use_instructions = False
    elif workbook_type == SS.STRUCTURE_KEY_DATA:
        if not data is None: use_instructions = False
    else: raise WorkbookTypeException(workbook_type)
    return instructions, use_instructions




def createAttributeCellContent(worksheet, row, col, attribute, item_type, item_type_specs, item_number, formats = None, format_key = None, temp_storage = None):
    """ Write default content into the cell of a worksheet corresponding to an attribute of an item. """

    # Determine attribute information and prepare for content production.
    attribute_spec = item_type_specs[item_type]["attributes"][attribute]
    if temp_storage is None: temp_storage = odict()
    if formats is None: raise OptimaException("Excel formats have not been passed to workbook table construction.")
    if format_key is None: format_key = ES.FORMAT_KEY_CENTER
    cell_format = formats[format_key]

    # Default content is blank.
    content = ""
    space = ""
    sep = ""
    validation_source = None
    rc = xw.utility.xl_rowcol_to_cell(row, col)

    # Set up default content type and reference information.
    content_type = None
    do_reference = False
    other_item_type = None
    other_attribute = None

    # Determine content type and prepare for referencing if appropriate.
    if "content_type" in attribute_spec: content_type = attribute_spec["content_type"]
    if isinstance(content_type, IDRefType):
        do_reference = True
        if not content_type.other_item_types is None:
            other_item_type = content_type.other_item_types[0]
            other_attribute = content_type.attribute
                  
    # Content associated with standard content types is set up here.
    if isinstance(content_type, IDType):
        # Prepare for referencing if this attribute has a superitem type.
        if not content_type.superitem_type is None:
            do_reference = True
            other_item_type = content_type.superitem_type
            other_attribute = attribute
        # Name and label attributes, i.e. those of ID type, reference earlier constructions of themselves if possible.
        # This is excluded for subitems due to their complicated form of content construction.
        if (not do_reference and item_type in temp_storage 
            and attribute in temp_storage[item_type] and len(temp_storage[item_type][attribute]["list_content"]) > item_number):
            do_reference = True       # Is not a reference type object but will allow one-to-one referencing to take place.
            other_item_type = item_type
            other_attribute = attribute
        # Otherwise construct content with a prefix if provided.
        else:
            content = str(item_number)     # The default content is the number of this item.
            if content_type.name_not_label:
                space = SS.DEFAULT_SPACE_NAME
                sep = SS.DEFAULT_SEPARATOR_NAME
            else:
                space = SS.DEFAULT_SPACE_LABEL
                sep = SS.DEFAULT_SEPARATOR_LABEL
            if "prefix" in attribute_spec:
                content = attribute_spec["prefix"] + space + content
    elif isinstance(content_type, SwitchType):
        validation_source = [SS.DEFAULT_SYMBOL_NO, SS.DEFAULT_SYMBOL_YES]
        if content_type.default_on: validation_source.reverse()
        content = validation_source[0]
    content_backup = content

    # References to other content are constructed here.
    if do_reference is True:
        list_id = item_number

        # Superitem-based references link subitem attributes to corresponding superitem attributes.
        # Because subitem displays are meant to be created instantly after superitems, the superitem referenced is the last one stored.
        if isinstance(content_type, IDType) and not content_type.superitem_type is None: list_id = -1

        # If there is another item type to reference, proceed with referencing its ID.
        if not other_item_type is None:
            try: stored_refs = temp_storage[other_item_type][other_attribute]
            except: raise InvalidReferenceException(item_type = item_type, attribute = attribute, ref_item_type = other_item_type, ref_attribute = other_attribute)
        
            # For one-to-one referencing, do not create content for tables that extend beyond the length of the referenced table.
            if len(stored_refs["list_content"]) > list_id:
                content_page = ""
                if not stored_refs["page_title"] == worksheet.name: content_page = "'{0}'!".format(stored_refs["page_title"])
                ref_content = "={0}{1}".format(content_page, stored_refs["list_cell"][list_id])
                ref_content_backup = stored_refs["list_content_backup"][list_id]

                if isinstance(content_type, IDType) and not content_type.superitem_type is None:
                    content = "=CONCATENATE({0},\"{1}\")".format(ref_content.lstrip("="), sep + content)
                    content_backup = ref_content_backup + sep + content_backup
                else:
                    content = ref_content
                    content_backup = ref_content_backup

        # If the content is marked to reference its own item type, append the ID to current content.
        # This reference should be to an ID of the same item a row ago.
        if isinstance(content_type, IDRefType) and content_type.self_referencing and item_number > 0: 
            list_id = item_number - 1
            try: stored_refs = temp_storage[item_type][content_type.attribute]
            except: raise InvalidReferenceException(item_type = item_type, attribute = attribute, ref_item_type = item_type, ref_attribute = content_type.attribute)
            content_page = ""
            if not stored_refs["page_title"] == worksheet.name: content_page = "'{0}'!".format(stored_refs["page_title"])
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

    # If content is of ID type, store it for referencing by other relevant attributes later.
    if isinstance(content_type, IDType):
        if not item_type in temp_storage: temp_storage[item_type] = {}
        if not attribute in temp_storage[item_type]: temp_storage[item_type][attribute] = {"list_content":[],"list_content_backup":[],"list_cell":[]}
        # Make sure the attribute does not already have stored values associated with it.
        if not len(temp_storage[item_type][attribute]["list_content"]) > item_number:
            temp_storage[item_type][attribute]["list_content"].append(content)
            temp_storage[item_type][attribute]["list_content_backup"].append(content_backup)
            temp_storage[item_type][attribute]["list_cell"].append(rc)
            temp_storage[item_type][attribute]["page_title"] = worksheet.name

    # Actually write the content, using a backup value where the content is an equation and may not be calculated.
    # This lack of calculation occurs when Excel files are not opened before writing and reading phases.
    # Also validate that the cell only allows certain values.
    if content.startswith("="):
        worksheet.write_formula(rc, content, cell_format, content_backup)
    else:
        worksheet.write(rc, content, cell_format)
    if not validation_source is None:
        worksheet.data_validation(rc, {"validate": "list", "source": validation_source})

def writeHeadersDC(worksheet, item_type, start_row, start_col, framework = None, data = None, workbook_type = None, formats = None, format_variables = None):
    
    item_type_specs = getWorkbookItemTypeSpecs(framework = framework, workbook_type = workbook_type)
    item_type_spec = item_type_specs[item_type]

    if formats is None: raise OptimaException("Excel formats have not been passed to workbook table construction.")
    if format_variables is None: format_variables = createDefaultFormatVariables()
    orig_format_variables = dcp(format_variables)
    format_variables = dcp(orig_format_variables)
    revert_format_variables = False

    row, col, header_column_map = start_row, start_col, odict()
    for attribute in item_type_spec["attributes"]:
        attribute_spec = item_type_spec["attributes"][attribute]
        if "ref_item_type" in attribute_spec:
            _, col, sub_map = writeHeadersDC(worksheet = worksheet, item_type = attribute_spec["ref_item_type"],
                                           start_row = row, start_col = col,
                                           framework = framework, data = data, workbook_type = workbook_type,
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
            worksheet.write(row, col, header, formats[ES.FORMAT_KEY_CENTER_BOLD])
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

def writeContentsDC(worksheet, item_type, start_row, header_column_map, framework = None, data = None, instructions = None, workbook_type = None,
                  formats = None, temp_storage = None):

    item_type_specs = getWorkbookItemTypeSpecs(framework = framework, workbook_type = workbook_type)
    item_type_spec = item_type_specs[item_type]
    instructions, use_instructions = makeInstructions(framework = framework, data = data, instructions = instructions, workbook_type = workbook_type)

    if temp_storage is None: temp_storage = odict()

    row, new_row = start_row, start_row
    if use_instructions:
        for item_number in range(instructions.num_items[item_type]):
            for attribute in item_type_spec["attributes"]:
                attribute_spec = item_type_spec["attributes"][attribute]
                if "ref_item_type" in attribute_spec:
                    sub_row = writeContentsDC(worksheet = worksheet, item_type = attribute_spec["ref_item_type"],
                                               start_row = row, header_column_map = header_column_map,
                                               framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                                               formats = formats, temp_storage = temp_storage)
                    new_row = max(new_row, sub_row)
                else:
                    col = header_column_map[attribute_spec["header"]]
                    createAttributeCellContent(worksheet = worksheet, row = row, col = col, 
                                               attribute = attribute, item_type = item_type, item_type_specs = item_type_specs, 
                                               item_number = item_number, formats = formats, temp_storage = temp_storage)
            row = max(new_row, row + 1)
    next_row = row
    return next_row

def writeDetailColumns(worksheet, core_item_type, start_row, start_col, framework = None, data = None, instructions = None, workbook_type = None, 
                       formats = None, format_variables = None, temp_storage = None):
    if temp_storage is None: temp_storage = odict()

    row, col = start_row, start_col
    row, _, header_column_map = writeHeadersDC(worksheet = worksheet, item_type = core_item_type, start_row = row, start_col = col,
                          framework = framework, data = data, workbook_type = workbook_type,
                          formats = formats, format_variables = format_variables)
    row = writeContentsDC(worksheet = worksheet, item_type = core_item_type, start_row = row, header_column_map = header_column_map,
                           framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                           formats = formats, temp_storage = temp_storage)
    next_row, next_col = row, col
    return next_row, next_col

def writeConnectionMatrix(worksheet, source_item_type, target_item_type, start_row, start_col, framework = None, data = None, instructions = None, workbook_type = None, 
                       formats = None, format_variables = None, temp_storage = None):
    item_type_specs = getWorkbookItemTypeSpecs(framework = framework, workbook_type = workbook_type)
    instructions, use_instructions = makeInstructions(framework = framework, data = data, instructions = instructions, workbook_type = workbook_type)

    if temp_storage is None: temp_storage = odict()

    row, col = start_row, start_col
    if use_instructions:
        source_row = start_row + 1
        for item_number in range(instructions.num_items[source_item_type]):
            createAttributeCellContent(worksheet = worksheet, row = source_row, col = start_col, 
                                       attribute = "name", item_type = source_item_type, item_type_specs = item_type_specs, 
                                       item_number = item_number, formats = formats, format_key = ES.FORMAT_KEY_CENTER_BOLD, temp_storage = temp_storage)
            source_row += 1
        target_col = start_col + 1
        for item_number in range(instructions.num_items[target_item_type]):
            createAttributeCellContent(worksheet = worksheet, row = start_row, col = target_col, 
                                       attribute = "name", item_type = target_item_type, item_type_specs = item_type_specs, 
                                       item_number = item_number, formats = formats, format_key = ES.FORMAT_KEY_CENTER_BOLD, temp_storage = temp_storage)
            target_col += 1
    row = source_row + 2    # Extra row to space out following tables.

    next_row, next_col = row, col
    return next_row, next_col

def writeHeadersTDVE(worksheet, item_type, item_key, start_row, start_col, framework = None, data = None, workbook_type = None, formats = None, format_variables = None):
    
    item_specs = getWorkbookItemSpecs(framework = framework, workbook_type = workbook_type)
    item_type_specs = getWorkbookItemTypeSpecs(framework = framework, workbook_type = workbook_type)
    
    if formats is None: raise OptimaException("Excel formats have not been passed to workbook table construction.")
    if format_variables is None: format_variables = createDefaultFormatVariables()
    orig_format_variables = dcp(format_variables)
    format_variables = dcp(orig_format_variables)
    
    row, col = start_row, start_col

    attribute = "label"
    attribute_spec = item_type_specs[item_type]["attributes"][attribute]
    for format_variable_key in format_variables:
        if format_variable_key in attribute_spec:
            format_variables[format_variable_key] = attribute_spec[format_variable_key]
    try: header = item_specs[item_type][item_key][attribute]
    except: raise OptimaException("No instantiation of item type '{0}' exists with the key of '{1}'.".format(item_type, item_key))
    worksheet.write(row, col, header, formats[ES.FORMAT_KEY_CENTER_BOLD])
    if "comment" in attribute_spec:
        header_comment = attribute_spec["comment"]
        worksheet.write_comment(row, col, header_comment, 
                                {"x_scale": format_variables[ES.KEY_COMMENT_XSCALE], 
                                 "y_scale": format_variables[ES.KEY_COMMENT_YSCALE]})
    worksheet.set_column(col, col, format_variables[ES.KEY_COLUMN_WIDTH])

    row += 1
    next_row = row
    return next_row

def writeContentsTDVE(worksheet, iterated_type, start_row, start_col, framework = None, data = None, instructions = None, workbook_type = None, formats = None, temp_storage = None):
    
    item_type_specs = getWorkbookItemTypeSpecs(framework = framework, workbook_type = workbook_type)
    instructions, use_instructions = makeInstructions(framework = framework, data = data, instructions = instructions, workbook_type = workbook_type)

    if temp_storage is None: temp_storage = odict()

    row, col = start_row, start_col
    if use_instructions:
        for item_number in range(instructions.num_items[iterated_type]):
            createAttributeCellContent(worksheet = worksheet, row = row, col = col, 
                                       attribute = "label", item_type = iterated_type, item_type_specs = item_type_specs, 
                                       item_number = item_number, formats = formats, temp_storage = temp_storage)
            row += 1
    row += 1    # Extra row to space out following tables.
    next_row = row
    return next_row

def writeTimeDependentValuesEntry(worksheet, item_type, item_key, iterated_type, start_row, start_col, framework = None, tvec=None, data = None, instructions = None, workbook_type = None, 
                       formats = None, format_variables = None, temp_storage = None):
    item_specs = getWorkbookItemSpecs(framework = framework, workbook_type = workbook_type)
    if temp_storage is None: temp_storage = odict()

    row, col = start_row, start_col

    # Create the standard value entry block, extracting the number of items from instructions.
    # TODO: Adjust this for when writing existing values to workbook.
    # TODO: Decide what to do about time. RS: I have put in a temporary solution
    instructions, use_instructions = makeInstructions(framework = framework, data = data, instructions = instructions, workbook_type = workbook_type)
    num_items = 0
    if use_instructions: num_items = instructions.num_items[iterated_type]
    default_values = [0.0]*num_items
    if "default_value" in item_specs[item_type][item_key]:
        default_values = [item_specs[item_type][item_key]["default_value"]]*num_items
    if tvec is None: tvec = [x for x in range(2000,2019)] # TODO Temporary, fix this!
    createValueEntryBlock(excel_page = worksheet, start_row = start_row, start_col = start_col + 1, 
                          num_items = num_items, time_vector = tvec, # TODO change nomenclature to use tvec everywhere
                          default_values = default_values, formats = formats)

    row = writeHeadersTDVE(worksheet = worksheet, item_type = item_type, item_key = item_key,
                                             start_row = row, start_col = col, 
                                             framework = framework, data = data, workbook_type = workbook_type,
                                             formats = formats, format_variables = format_variables)
    row = writeContentsTDVE(worksheet = worksheet, iterated_type = iterated_type, start_row = row, start_col = col,
                           framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                           formats = formats, temp_storage = temp_storage)

    next_row, next_col = row, col
    return next_row, next_col

def writeTable(worksheet, table, start_row, start_col, framework = None, tvec=None, data = None, instructions = None, workbook_type = None, 
               formats = None, format_variables = None, temp_storage = None):

    # Check workbook type.
    if workbook_type not in [SS.STRUCTURE_KEY_FRAMEWORK, SS.STRUCTURE_KEY_DATA]: raise WorkbookTypeException(workbook_type)

    if temp_storage is None: temp_storage = odict()

    row, col = start_row, start_col
    if isinstance(table, DetailColumns):
        row, col = writeDetailColumns(worksheet = worksheet, core_item_type = table.item_type, start_row = row, start_col = col,
                                      framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                                      formats = formats, format_variables = format_variables, temp_storage = temp_storage)
    if isinstance(table, ConnectionMatrix):
        row, col = writeConnectionMatrix(worksheet = worksheet, source_item_type = table.source_item_type, target_item_type = table.target_item_type,
                                         start_row = row, start_col = col, 
                                         framework = framework, data = data, instructions = instructions, workbook_type = workbook_type,
                                         formats = formats, format_variables = format_variables, temp_storage = temp_storage)
    if isinstance(table, TimeDependentValuesEntry):
        if not table.item_key is None:
            row, col = writeTimeDependentValuesEntry(worksheet = worksheet, item_type = table.item_type, item_key = table.item_key, iterated_type = table.iterated_type,
                                                     start_row = row, start_col = col, 
                                                     framework = framework, tvec=tvec, data = data, instructions = instructions, workbook_type = workbook_type,
                                                     formats = formats, format_variables = format_variables, temp_storage = temp_storage)
    
    next_row, next_col = row, col
    return next_row, next_col

def writeWorksheet(workbook, page_key, framework=None, tvec=None, data=None, instructions=None, workbook_type=None, 
                   formats=None, format_variables=None, temp_storage=None):

    page_spec = getWorkbookPageSpec(page_key = page_key, framework = framework, workbook_type = workbook_type)

    # Construct worksheet.
    page_title = page_spec["title"]
    logger.info("Creating page: {0}".format(page_title))
    worksheet = workbook.add_worksheet(page_title)

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

    if temp_storage is None: temp_storage = odict()

    # Iteratively construct tables.
    row, col = 0, 0
    for table in page_spec["tables"]:
        row, col = writeTable(worksheet = worksheet, table = table, start_row = row, start_col = col,
                              framework = framework, tvec=tvec, data = data, instructions = instructions, workbook_type = workbook_type,
                              formats = formats, format_variables = format_variables, temp_storage = temp_storage)

@accepts(str)
def writeWorkbook(workbook_path, framework=None, tvec=None, data=None, instructions=None, workbook_type=None):

    page_keys = getWorkbookPageKeys(framework = framework, workbook_type = workbook_type)

    logger.info("Constructing a {0}: {1}".format(displayName(workbook_type), workbook_path))

    # Construct workbook and related formats.
    prepareFilePath(workbook_path)
    workbook = xw.Workbook(workbook_path)
    formats = createStandardExcelFormats(workbook)
    format_variables = createDefaultFormatVariables()

    # Create a storage dictionary for values and formulae that may persist between sections.
    temp_storage = odict()

    # Iteratively construct worksheets.
    for page_key in page_keys:
        writeWorksheet(workbook=workbook, page_key=page_key, 
                       framework=framework, tvec=tvec, data=data, instructions=instructions, workbook_type=workbook_type,
                       formats=formats, format_variables=format_variables, temp_storage=temp_storage)
    workbook.close()

    logger.info("{0} construction complete.".format(displayName(workbook_type, as_title = True)))