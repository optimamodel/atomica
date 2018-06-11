import os
import numpy as np

import xlrd
import sciris.core as sc
from xlsxwriter.utility import xl_rowcol_to_cell as xlrc

from .excel import ExcelSettings as ES
from .excel import extract_header_columns_mapping, extract_excel_sheet_value
from .structure import KeyData, SemanticUnknownException
from .structure_settings import DetailColumns, TableTemplate, ConnectionMatrix, TimeDependentValuesEntry, \
    SwitchType, QuantityFormatType
from .system import SystemSettings as SS
from .system import logger, AtomicaException, accepts, display_name
from .workbook_utils import WorkbookTypeException, WorkbookRequirementException, get_workbook_page_keys, \
    get_workbook_page_specs, get_workbook_page_spec, get_workbook_item_type_specs, get_workbook_item_specs


def get_target_structure(framework=None, data=None, workbook_type=None):
    """ Returns the structure to store definitions and values being read from workbook. """
    if workbook_type == SS.STRUCTURE_KEY_FRAMEWORK:
        if framework is None:
            raise WorkbookRequirementException(workbook_type=SS.STRUCTURE_KEY_FRAMEWORK,
                                               requirement_type="ProjectFramework")
        else:
            structure = framework
    elif workbook_type == SS.STRUCTURE_KEY_DATA:
        if data is None:
            raise WorkbookRequirementException(workbook_type=SS.STRUCTURE_KEY_DATA, requirement_type="ProjectData")
        else:
            structure = data
    else:
        raise WorkbookTypeException(workbook_type)
    return structure


def read_contents_dc(worksheet, table, start_row, header_columns_map, item_type=None, stop_row=None, framework=None,
                     data=None, workbook_type=None, superitem_type_name_pairs=None):
    if item_type is None:
        item_type = table.item_type
    item_type_specs = get_workbook_item_type_specs(framework=framework, workbook_type=workbook_type)
    item_type_spec = item_type_specs[item_type]

    structure = get_target_structure(framework=framework, data=data, workbook_type=workbook_type)
    if superitem_type_name_pairs is None:
        superitem_type_name_pairs = []

    row = start_row
    item_name = ""
    if stop_row is None:
        stop_row = worksheet.nrows
    while row < stop_row:
        # Only the first column matters for a name.
        name_col = header_columns_map[item_type_spec["attributes"]["name"]["header"]][0]
        test_name = str(worksheet.cell_value(row, name_col))
        if not test_name == "":
            item_name = test_name
        else:
            # If the name entry is blank, scan the entire row.
            check_col = 0
            while check_col < worksheet.ncols:
                # If there is something to parse, e.g. a subitem, then proceed with parsing.
                if not str(worksheet.cell_value(row, check_col)) == "":
                    break
                # If the final column is reached and everything is blank, stop reading the table.
                if check_col == worksheet.ncols - 1:
                    next_row = row + 1
                    return next_row
                check_col += 1
        if not item_name == "":
            try:
                structure.get_spec(item_name)
            except Exception:
                structure.create_item(item_name=item_name, item_type=item_type,
                                      superitem_type_name_pairs=superitem_type_name_pairs)
            for attribute in item_type_spec["attributes"]:
                # No need to parse name.
                # Ignore explicitly excluded attributes or implicitly not-included attributes for table construction.
                if attribute == "name" or (table.exclude_not_include == (attribute in table.attribute_list)):
                    continue
                attribute_spec = item_type_spec["attributes"][attribute]
                if "ref_item_type" in attribute_spec:
                    new_superitem_type_name_pairs = sc.dcp(superitem_type_name_pairs)
                    new_superitem_type_name_pairs.append([item_type, item_name])
                    read_contents_dc(worksheet=worksheet, table=table, item_type=attribute_spec["ref_item_type"],
                                     start_row=row, header_columns_map=header_columns_map, stop_row=row + 1,
                                     framework=framework, data=data, workbook_type=workbook_type,
                                     superitem_type_name_pairs=new_superitem_type_name_pairs)
                else:
                    try:
                        start_col, last_col = header_columns_map[attribute_spec["header"]]
                    except KeyError:
                        logger.warning("Workbook import process could not locate attribute '{0}' for '{1}' item '{2}' "
                                       "when parsing a detail-columns table. Ignoring and proceeding to next "
                                       "attribute.".format(attribute, item_type, item_name))
                        continue
                    content_type = attribute_spec["content_type"]
                    filters = []
                    if content_type is not None:
                        if content_type.is_list:
                            filters.append(ES.FILTER_KEY_LIST)
                        if isinstance(content_type, SwitchType):
                            if content_type.default_on:
                                filters.append(ES.FILTER_KEY_BOOLEAN_NO)
                            else:
                                filters.append(ES.FILTER_KEY_BOOLEAN_YES)
                    # For ease of coding, values for this table can span multiple columns but not rows.
                    value = extract_excel_sheet_value(worksheet, start_row=row, start_col=start_col,
                                                      stop_col=last_col + 1, filters=filters)
                    if isinstance(content_type, QuantityFormatType) and value is not None:
                        value = value.lower()  # A catch to ensure formats are stored as lower-case strings.
                    if value is not None or (content_type is not None and content_type.default_value is not None):
                        structure.set_spec_value(term=item_name, attribute=attribute, value=value,
                                                 content_type=content_type)
            row += 1
    next_row = row
    return next_row


def read_detail_columns(worksheet, table, start_row, framework=None, data=None, workbook_type=None):
    row = start_row
    header_columns_map = extract_header_columns_mapping(worksheet, row=row)
    row += 1
    row = read_contents_dc(worksheet=worksheet, table=table, start_row=row, header_columns_map=header_columns_map,
                           framework=framework, data=data, workbook_type=workbook_type)
    next_row = row
    return next_row


def read_connection_matrix(worksheet, table, start_row, framework=None, data=None, workbook_type=None):
    """
    Parse a connection matrix, whether standard or template.

    Note that items with names referred to by connection matrices must be constructed first.
    Ensure a logical read order in structure settings, even for different display order.
    In practice, this means a relevant 'detail columns' table should get parsed before associated matrices.
    """
    item_type_specs = get_workbook_item_type_specs(framework=framework, workbook_type=workbook_type)
    structure = get_target_structure(framework=framework, data=data, workbook_type=workbook_type)

    header_row, header_col = None, 0
    row, col = start_row, header_col + 1
    last_col = None
    term = None
    while row < worksheet.nrows:
        # Scan for header row of matrix, recognising top-left cell may be empty, hence the non-zero start column.
        if header_row is None:
            check_label = str(worksheet.cell_value(row, col))
            if not check_label == "":
                header_row = row
                # If this table is a deferred-instantiation template, it relates to an item with key in the corner.
                # Extract that term.
                if table.template_item_type is not None:
                    term = str(worksheet.cell_value(header_row, header_col))
                # Upon finding the header row, locate its last column.
                col += 1
                while last_col is None and col < worksheet.ncols:
                    check_label = str(worksheet.cell_value(row, col))
                    if check_label == "":
                        last_col = col - 1
                    col += 1
                if last_col is None:
                    last_col = worksheet.ncols - 1
        else:
            source_item = str(worksheet.cell_value(row, header_col))
            # If there is no source item, the connection matrix must have ended.
            if source_item == "":
                break
            for col in range(header_col + 1, last_col + 1):
                target_item = str(worksheet.cell_value(header_row, col))
                val = str(worksheet.cell_value(row, col))
                # For standard connection matrices, item names related to connections are pulled from non-empty cells.
                if table.template_item_type is None:
                    if not val == "":
                        structure.append_spec_value(term=val, attribute=table.storage_attribute,
                                                    value=(source_item, target_item))
                # For template connection matrices, the item name is in the 'corner' header.
                # Attach connections to that item in specs if a connection exists, i.e. is marked by 'y'.
                else:
                    if val == SS.DEFAULT_SYMBOL_YES:
                        structure.append_spec_value(term=term, attribute=table.storage_attribute,
                                                    value=(source_item, target_item))
        row += 1
    next_row = row
    return next_row


def read_time_dependent_values_entry(worksheet, table, start_row,
                                     framework=None, data=None, workbook_type=None):
    item_specs = get_workbook_item_specs(framework=framework, workbook_type=workbook_type)
    structure = get_target_structure(framework=framework, data=data, workbook_type=workbook_type)

    item_type = table.template_item_type
    item_key = table.template_item_key
    value_attribute = table.value_attribute

    row, id_col = start_row, 0
    block_col = 1   # Column increment at which data entry block begins.
    if table.iterate_over_links:
        block_col = 3

    keep_scanning = True
    header_row = None
    term = None         # The header for this entire table.
    data_key = None     # The key with which to store data provided within a row of this table.
    while keep_scanning and row < worksheet.nrows:
        label = str(worksheet.cell_value(row, id_col))
        if not label == "":
            # The first label encounter is of the item that heads this table.
            # Verify it matches the item name associated with the table, provided no deferred instantiation took place.
            if header_row is None:
                if item_key is not None and not label == item_specs[item_type][item_key]["label"]:
                    raise AtomicaException(
                        "A time-dependent value entry table was expected in sheet '{0}' for item code-named '{1}'. "
                        "Workbook parser encountered a table headed by label '{2}' instead.".format(worksheet.name,
                                                                                                    item_key, label))
                else:
                    term = label
                    # Do a quick scan of all row headers to determine keys for a TimeSeries object.
                    quick_scan = True
                    quick_row = row + 1
                    keys = []
                    while quick_scan and quick_row < worksheet.nrows:
                        quick_label = str(worksheet.cell_value(quick_row, id_col))
                        if quick_label == "":
                            quick_scan = False
                        elif quick_label == SS.DEFAULT_SYMBOL_IGNORE:
                            pass
                        else:
                            # If table iterates over tupled items rather that just items, the tupled name pair is key.
                            if table.iterate_over_links:
                                keys.append((structure.get_spec_name(quick_label),
                                             structure.get_spec_name(str(worksheet.cell_value(quick_row, id_col + 2)))))
                            else:
                                keys.append(structure.get_spec_name(quick_label))
                        quick_row += 1
                    # Check if the item already exists in parsed structure, which it must if instantiation is deferred.
                    # If not, the item key is the name and the header is the label; construct an item.
                    if item_key is not None:
                        try:
                            structure.get_spec(term=item_key)
                        except SemanticUnknownException:
                            structure.create_item(item_name=item_key, item_type=item_type)
                            structure.set_spec_value(term=item_key, attribute="label", value=label)
                    time_series = KeyData(keys=keys)
                    structure.set_spec_value(term=term, attribute=value_attribute, value=time_series)
                header_row = row
            # All other label encounters are of an iterated type.
            else:
                if label == SS.DEFAULT_SYMBOL_IGNORE:
                    row += 1
                    continue
                # Time series keys for standard items are their names.
                data_key = structure.get_spec_name(label)
                # Keys for time series that involve links between items are tuple-pairs of their names.
                if table.iterate_over_links:
                    data_key =(data_key, structure.get_spec_name(str(worksheet.cell_value(row, id_col+2))))
                col = id_col + block_col
                while col < worksheet.ncols:
                    val = str(worksheet.cell_value(row, col))
                    if val not in [SS.DEFAULT_SYMBOL_INAPPLICABLE, SS.DEFAULT_SYMBOL_OR, ""]:
                        header = str(worksheet.cell_value(header_row, col))
                        if header == ES.QUANTITY_TYPE_HEADER:
                            structure.get_spec(term=term)[value_attribute].set_format(
                                key=data_key, value_format=val.lower())
                            col += 1
                            continue
                        try:
                            val = float(val)
                        except ValueError:
                            raise AtomicaException("Workbook parser encountered invalid value '{0}' in cell '{1}' "
                                                   "of sheet '{2}'.".format(val, xlrc(row, col), worksheet.name))
                        if header == ES.ASSUMPTION_HEADER:
                            structure.get_spec(term=term)[value_attribute].set_value(
                                key=data_key, value=val)
                        else:
                            try:
                                time = float(header)
                            except ValueError:
                                raise AtomicaException("Workbook parser encountered invalid time header '{0}' in cell "
                                                       "'{1}' of sheet '{2}'.".format(header, xlrc(header_row, col),
                                                                                      worksheet.name))
                            structure.get_spec(term=term)[value_attribute].set_value(
                                key=data_key, value=val, t=time)
                    col += 1

        else:
            if header_row is not None:
                keep_scanning = False
        row += 1
    next_row = row
    return next_row


def read_table(worksheet, table, start_row, start_col, framework=None, data=None, workbook_type=None):
    # Check workbook type.
    if workbook_type not in [SS.STRUCTURE_KEY_FRAMEWORK, SS.STRUCTURE_KEY_DATA]:
        raise WorkbookTypeException(workbook_type)
    structure = get_target_structure(framework=framework, data=data, workbook_type=workbook_type)

    row, col = start_row, start_col
    if isinstance(table, DetailColumns):
        row = read_detail_columns(worksheet=worksheet, table=table, start_row=row,
                                  framework=framework, data=data, workbook_type=workbook_type)
    if isinstance(table, TableTemplate):
        iteration_amount = 1
        # If the table was templated with deferred instantiation...
        if table.template_item_type is not None:
            # Check if instantiation is deferred.
            # If it is, iterate for the number of template-related items already constructed.
            # Note that this is dangerous if the items are constructed later.
            # It is dev responsibility to ensure structure settings have relevant detail columns tables parsed first.
            if table.template_item_key is None:
                iteration_amount = len(structure.specs[table.template_item_type])
        if isinstance(table, ConnectionMatrix):
            for iteration in range(iteration_amount):
                row = read_connection_matrix(worksheet=worksheet, table=table, start_row=row,
                                             framework=framework, data=data, workbook_type=workbook_type)
        if isinstance(table, TimeDependentValuesEntry):
            for iteration in range(iteration_amount):
                row = read_time_dependent_values_entry(worksheet=worksheet, table=table, start_row=row,
                                                       framework=framework, data=data, workbook_type=workbook_type)

    next_row, next_col = row, col
    return next_row, next_col


def read_worksheet(workbook, page_key, framework=None, data=None, workbook_type=None):
    page_spec = get_workbook_page_spec(page_key=page_key, framework=framework, workbook_type=workbook_type)
    if len(page_spec["tables"]) == 0:
        return
    page_title = page_spec["label"]
    try:
        worksheet = workbook.sheet_by_name(page_title)
        logger.info("Importing page: {0}".format(page_title))
    except xlrd.biffh.XLRDError:
        if "can_skip" in page_spec and page_spec["can_skip"] is True:
            logger.warning("Workbook does not contain an optional page titled '{0}'.".format(page_title))
            return
        logger.error("Workbook does not contain a required page titled '{0}'.".format(page_title))
        raise

    # Iteratively parse tables.
    row, col = 0, 0
    for table in page_spec["tables"]:
        row, col = read_table(worksheet=worksheet, table=table, start_row=row, start_col=col,
                              framework=framework, data=data, workbook_type=workbook_type)

    # TODO: Consider whether this should be a warning rather than an exception.
    if row < worksheet.nrows:
        raise AtomicaException("Workbook parser has concluded for page '{0}' before row {1}, even though worksheet "
                               "has {2} rows. An errant blank row may have truncated table "
                               "parsing.".format(worksheet.name, row, worksheet.nrows))


def read_reference_worksheet(workbook):
    """
    Reads a hidden worksheet for metadata and other values that are useful to store.
    These values are not directly part of framework/data.
    """

    page_title = "metadata".title()
    try:
        worksheet = workbook.sheet_by_name(page_title)
        logger.info("Importing page: {0}".format(page_title))
    except xlrd.biffh.XLRDError:
        logger.warn("No metadata page exists in this workbook.")
        return None

    metadata = dict()
    row = 0
    while row < worksheet.nrows:
        value = str(worksheet.cell_value(row, 1))
        try:
            value = float(value)
        except ValueError:
            pass
        metadata[str(worksheet.cell_value(row, 0))] = value
        row += 1
    return metadata


@accepts(str)
def read_workbook(workbook_path, framework=None, data=None, workbook_type=None):
    page_keys = get_workbook_page_keys(framework=framework, workbook_type=workbook_type)
    page_specs = get_workbook_page_specs(framework=framework, workbook_type=workbook_type)
    page_keys = sorted(page_keys,
                       key=lambda x: page_specs[x]["read_order"] if not page_specs[x]["read_order"] is None else 0)

    logger.info("Importing a {0}: {1}".format(display_name(workbook_type), workbook_path))

    workbook_path = os.path.abspath(workbook_path)
    try:
        workbook = xlrd.open_workbook(workbook_path)
    except:
        raise AtomicaException("Workbook was not found.")

    # Check workbook type and initialise output
    if workbook_type not in [SS.STRUCTURE_KEY_FRAMEWORK, SS.STRUCTURE_KEY_DATA]:
        raise WorkbookTypeException(workbook_type)

    # Iteratively parse worksheets.
    for page_key in page_keys:
        read_worksheet(workbook=workbook, page_key=page_key,
                       framework=framework, data=data, workbook_type=workbook_type)

    structure = get_target_structure(framework=framework, data=data, workbook_type=workbook_type)
    structure.complete_specs(framework=framework)
    structure.frameworkfilename = workbook_path

    metadata = read_reference_worksheet(workbook=workbook)

    return metadata



#%% COMPLETELY SEPARATE CODE TO READ IN A WORKBOOK WITH PROGRAMS DATA - NEEDS TO BE MERGED WITH THE ABOVE

def getyears(sheetdata):
    ''' Get years from a worksheet'''
    years = [] # Initialize epidemiology data years
    for col in range(sheetdata.ncols):
        thiscell = sheetdata.cell_value(1,col) # 1 is the 2nd row which is where the year data should be
        if thiscell=='' and len(years)>0: #  We've gotten to the end
            lastdatacol = col # Store this column number
            break # Quit
        elif thiscell != '': # Nope, more years, keep going
            years.append(float(thiscell)) # Add this year
    
    return lastdatacol, years
   
   
def blank2newtype(thesedata, newtype=None):
    ''' Convert a blank entry to another type, e.g. nan, None or zero'''
    if newtype is None or newtype=='nan': newval = np.nan # For backward compatability
    elif newtype=='None': newval = None
    elif newtype=='zero': newval = 0
    elif sc.isnumber(newtype): newval = newtype
    else: 
        errormsg = 'Cannot convert blanks to type %s, can only convert to types [''nan'', ''None'', ''zero''] or numbers' % (type(newtype)) 
        raise AtomicaException(errormsg)
    return [newval if thisdatum=='' else thisdatum for thisdatum in thesedata ]
    

def validatedata(thesedata, sheetname, thispar, row, checkupper=False, checklower=True, checkblank=True, startcol=0):
    ''' Do basic validation on the data: at least one point entered, between 0 and 1 or just above 0 if checkupper=False '''
    
    result = sc.odict()
    result['isvalid'] = 1
    # Check that only numeric data have been entered
    for column,datum in enumerate(thesedata):
        if not sc.isnumber(datum):
            errormsg = 'Invalid entry in sheet "%s", parameter "%s":\n' % (sheetname, thispar) 
            errormsg += 'row=%i, column=%s, value="%s"\n' % (row+1, xlrd.colname(column+startcol), datum)
            errormsg += 'Be sure all entries are numeric'
            if ' ' or '\t' in datum: errormsg +=' (there seems to be a space or tab)'
            raise AtomicaException(errormsg)
    
    # Now check integrity of data itself
    validdata = np.array(thesedata)[~np.isnan(thesedata)]
    if len(validdata):
        valid = np.array([True]*len(validdata)) # By default, set everything to valid
        if checklower: valid *= np.array(validdata)>=0
        if checkupper: valid *= np.array(validdata)<=1
        if not valid.all():
            invalid = validdata[valid==False]
            errormsg = 'Invalid entry in sheet "%s", parameter "%s":\n' % (sheetname, thispar) 
            errormsg += 'row=%i, invalid="%s", values="%s"\n' % (row+1, invalid, validdata)
            errormsg += 'Be sure that all values are >=0 (and <=1 if a probability)'
            result['isvalid'] = 0
            result['errormsg'] = errormsg
    elif checkblank: # No data entered
        errormsg = 'No data or assumption entered for sheet "%s", parameter "%s", row=%i' % (sheetname, thispar, row) 
        result['isvalid'] = 0
        result['errormsg'] = errormsg
    return result


def load_progbook(filename, verbose=2):
    '''
    Loads programs book (i.e. reads its contents into the data).
    '''
    ## Basic setup
    data = sc.odict() # Create structure for holding data

    ## Read in databook 
    try: workbook = xlrd.open_workbook(filename) # Open workbook
    except: 
        errormsg = 'Failed to load program spreadsheet: file "%s" not found or other problem' % filename
        raise AtomicaException(errormsg)
    
    ## Calculate columns for which data are entered, and store the year ranges
    sheetdata = workbook.sheet_by_name('Program spend data') # Load this workbook
    lastdatacol, data['years'] = getyears(sheetdata)
    assumptioncol = lastdatacol + 1 # Figure out which column the assumptions are in; the "OR" space is in between
    
    ## Load program spend information
    sheetdata = workbook.sheet_by_name('Populations & programs') # Load 
    data['progs'] = sc.odict()
    data['pars'] = sc.odict()
    data['progs']['short'] = []
    data['progs']['name'] = []
    data['progs']['target_pops'] = []
    data['progs']['target_comps'] = []
    
    colindices = []
    for row in range(sheetdata.nrows): 
        if sheetdata.cell_value(row,0)!='':
            for col in range(2,sheetdata.ncols):
                cell_val = sheetdata.cell(row, col).value
                if cell_val!='': colindices.append(col-1)
        else:
            thesedata = sheetdata.row_values(row, start_colx=2) 
        
            if row==1:
                data['pops'] = thesedata[3:colindices[0]]
                data['comps'] = thesedata[colindices[1]-1:]
            else:
                if thesedata[0]:
                    progname = str(thesedata[0])
                    data['progs']['short'].append(progname)
                    data['progs']['name'].append(str(thesedata[1]))
                    data['progs']['target_pops'].append(thesedata[3:colindices[0]])
                    data['progs']['target_comps'].append(blank2newtype(thesedata[colindices[1]-1:],0))
                    data[progname] = sc.odict()
                    data[progname]['name'] = str(thesedata[1])
                    data[progname]['target_pops'] = thesedata[3:colindices[0]]
                    data[progname]['target_comps'] = blank2newtype(thesedata[colindices[1]-1:], 0)
                    data[progname]['spend'] = []
                    data[progname]['basespend'] = []
                    data[progname]['capacity'] = []
                    data[progname]['unitcost'] = sc.odict()
    
    namemap = {'Total spend': 'spend',
               'Base spend':'basespend',
               'Unit cost':'unitcost',
               'Capacity constraints': 'capacity'} 
    validunitcosts = sc.odict()
    
    for row in range(sheetdata.nrows): 
        sheetname = sheetdata.cell_value(row,0) # Sheet name
        progname = sheetdata.cell_value(row, 1) # Get the name of the program

        if progname != '': # The first column is blank: it's time for the data
            validunitcosts[progname] = []
            thesedata = blank2newtype(sheetdata.row_values(row, start_colx=3, end_colx=lastdatacol)) # Data starts in 3rd column, and ends lastdatacol-1
            assumptiondata = sheetdata.cell_value(row, assumptioncol)
            if assumptiondata != '': # There's an assumption entered
                thesedata = [assumptiondata] # Replace the (presumably blank) data if a non-blank assumption has been entered
            if sheetdata.cell_value(row, 2) in namemap.keys(): # It's a regular variable without ranges
                thisvar = namemap[sheetdata.cell_value(row, 2)]  # Get the name of the indicator
                data[progname][thisvar] = thesedata # Store data
            else:
                thisvar = namemap[sheetdata.cell_value(row, 2).split(': ')[0]]  # Get the name of the indicator
                thisestimate = sheetdata.cell_value(row, 2).split(': ')[1]
                data[progname][thisvar][thisestimate] = thesedata # Store data
            checkblank = False if thisvar in ['basespend','capacity'] else True # Don't check optional indicators, check everything else
            result = validatedata(thesedata, sheetname, thisvar, row, checkblank=checkblank)
            if thisvar in namemap.keys():
                if result['isvalid']==0: raise AtomicaException(result['errormsg'])
            elif thisvar=='unitcost': # For some variables we need to compare several
                if result['isvalid']==0: validunitcosts.append(result['isvalid'])
    
    for progname in data['progs']['short']:
        if validunitcosts[progname] in [[0,0,0],[0,0,1],[0,1,0]]:
            errormsg = 'You need to enter either best+low+high, best, or low+high values for the unit costs. Values are incorrect for program %s' % (progname) 
            raise AtomicaException(errormsg)

            
    ## Load parameter information
    sheetdata = workbook.sheet_by_name('Program effects') # Load 
    for row in range(sheetdata.nrows): 
        if sheetdata.cell_value(row, 0)!='':
            par_name = sheetdata.cell_value(row, 0) # Get the name of the parameter
        elif sheetdata.cell_value(row, 1)!='': # Data row
            pop_name = sheetdata.cell_value(row, 1)
            data['pars'][par_name] = sc.odict()
            data['pars'][par_name][pop_name] = sc.odict()
            data['pars'][par_name][pop_name]['interactions'] = sheetdata.row_values(row, start_colx=2, end_colx=4) 
            data['pars'][par_name][pop_name]['npi_val'] = [sheetdata.cell_value(row+i, 5) if sheetdata.cell_value(row+i, 5)!='' else np.nan for i in range(3)]
            data['pars'][par_name][pop_name]['max_val'] = [sheetdata.cell_value(row+i, 6) if sheetdata.cell_value(row+i, 6)!='' else np.nan for i in range(3)]
            data['pars'][par_name][pop_name]['prog_vals'] = [blank2newtype(sheetdata.row_values(row+i, start_colx=8, end_colx=8+len(data['progs']['short'])) ) for i in range(3)]

    return data




