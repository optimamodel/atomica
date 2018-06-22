# -*- coding: utf-8 -*-
"""
Atomica Excel utilities file.
Contains functionality specific to Excel input and output.
"""

from .system import SystemSettings as SS
from .system import logger, log_usage, accepts, returns, AtomicaException

import xlsxwriter as xw
from xlsxwriter.utility import xl_rowcol_to_cell as xlrc
import xlrd


class ExcelSettings(object):
    """ Stores settings relevant to Excel file input and output. """

    FILE_EXTENSION = ".xlsx"
    LIST_SEPARATOR = ","

    # Filter keys that denote special extraction rules when reading in Excel sheets.
    FILTER_KEY_LIST = "filter_list"
    FILTER_KEY_BOOLEAN_YES = "boolean_yes"  # Extracted value is True for a yes symbol and False for anything else.
    FILTER_KEY_BOOLEAN_NO = "boolean_no"  # Extracted value is False for a no symbol and True for anything else.

    # Keys for float-valued variables related in some way to Excel file formatting.
    # They must have corresponding default values.
    # TODO: Work out how to reference the keys here within the configuration file, so as to keep the two aligned.
    KEY_COLUMN_WIDTH = "column_width"
    KEY_COMMENT_XSCALE = "comment_xscale"
    KEY_COMMENT_YSCALE = "comment_yscale"
    FORMAT_VARIABLE_KEYS = [KEY_COLUMN_WIDTH, KEY_COMMENT_XSCALE, KEY_COMMENT_YSCALE]

    FORMAT_KEY_CENTER = "center"
    FORMAT_KEY_CENTER_BOLD = "center_bold"

    EXCEL_IO_DEFAULT_COLUMN_WIDTH = 20
    EXCEL_IO_DEFAULT_COMMENT_XSCALE = 3
    EXCEL_IO_DEFAULT_COMMENT_YSCALE = 3

    # Details for the value entry block function.
    # TODO: Consider shifting this to table specs in structure settings.
    ASSUMPTION_HEADER = "constant".title()
    ASSUMPTION_COLUMN_WIDTH = 10
    ASSUMPTION_COMMENT_XSCALE = 3
    ASSUMPTION_COMMENT_YSCALE = 3
    ASSUMPTION_COMMENT = ("This column should be filled with default values used by the model.\n"
                          "If the option to provide time-dependent values exists, then "
                          "this can be considered a time-independent assumption.\n"
                          "In this case, if any time-dependent values are entered, the "
                          "Excel sheet will attempt to explicitly mark the corresponding "
                          "cell as inapplicable.\n"
                          "Time-dependent values always trump assumptions.")
    QUANTITY_TYPE_HEADER = "quantity_type".replace("_", " ").title()
    QUANTITY_TYPE_COLUMN_WIDTH = 15
    QUANTITY_TYPE_COMMENT_XSCALE = 3
    QUANTITY_TYPE_COMMENT_YSCALE = 3
    QUANTITY_TYPE_COMMENT = ("This column displays the type of quantity that the databook is "
                             "requesting, e.g. probability, duration, number, etc.\n"
                             "In some cases, the user may select the format for the data, "
                             "to align with data collection pragmatics, and appropriate "
                             "conversions will be done internally to the model.")


# Utility functions for writing.

@log_usage
@accepts(xw.Workbook)
def create_standard_excel_formats(excel_file):
    """ 
    Generates and returns a dictionary of standard excel formats attached to an excel file.
    Note: Can be modified or expanded as necessary to fit other definitions of 'standard'.
    """
    formats = dict()
    formats[ExcelSettings.FORMAT_KEY_CENTER_BOLD] = excel_file.add_format({"align": "center", "bold": True})
    formats[ExcelSettings.FORMAT_KEY_CENTER] = excel_file.add_format({"align": "center"})
    return formats


@log_usage
def create_default_format_variables():
    """
    Establishes framework-file default values for format variables in a dictionary and returns it.
    Note: Once used exec function here but it is now avoided for Python3 compatibility.
    """
    format_variables = dict()
    format_variables[ExcelSettings.KEY_COLUMN_WIDTH] = ExcelSettings.EXCEL_IO_DEFAULT_COLUMN_WIDTH
    format_variables[ExcelSettings.KEY_COMMENT_XSCALE] = ExcelSettings.EXCEL_IO_DEFAULT_COMMENT_XSCALE
    format_variables[ExcelSettings.KEY_COMMENT_YSCALE] = ExcelSettings.EXCEL_IO_DEFAULT_COMMENT_YSCALE
    return format_variables


def create_value_entry_block(excel_page, start_row, start_col, num_items,
                             time_vector=None, default_values=None, quantity_types=None,
                             condition_list=None, formats=None):
    """
    Create a block where users enter values in a 'constant' column or as time-dependent array.
    A list of Excel-string conditions can be provided that decide, if true, that a row appears.
    """
    # Generate standard formats if they do not exist.
    if formats is None:
        logger.warning("Formats were not passed to worksheet value-entry block construction.")
        formats = {ExcelSettings.FORMAT_KEY_CENTER_BOLD: None, ExcelSettings.FORMAT_KEY_CENTER: None}

    if time_vector is None:
        time_vector = []
    if default_values is None:
        default_values = [0.0] * num_items
    if condition_list is None:
        condition_list = [None] * num_items

    # Start with the headers and column formats.
    row, col = start_row, start_col
    # If a list of quantity types exists for the data, create a corresponding column.
    if quantity_types is not None:
        excel_page.write(row, col, ExcelSettings.QUANTITY_TYPE_HEADER, formats[ExcelSettings.FORMAT_KEY_CENTER_BOLD])
        excel_page.write_comment(row, col, ExcelSettings.QUANTITY_TYPE_COMMENT,
                                 {"x_scale": ExcelSettings.QUANTITY_TYPE_COMMENT_XSCALE,
                                  "y_scale": ExcelSettings.QUANTITY_TYPE_COMMENT_YSCALE})
        excel_page.set_column(col, col, ExcelSettings.QUANTITY_TYPE_COLUMN_WIDTH)
        col += 1
    excel_page.write(row, col, ExcelSettings.ASSUMPTION_HEADER, formats[ExcelSettings.FORMAT_KEY_CENTER_BOLD])
    excel_page.write_comment(row, col, ExcelSettings.ASSUMPTION_COMMENT,
                             {"x_scale": ExcelSettings.ASSUMPTION_COMMENT_XSCALE,
                              "y_scale": ExcelSettings.ASSUMPTION_COMMENT_YSCALE})
    excel_page.set_column(col, col, ExcelSettings.ASSUMPTION_COLUMN_WIDTH)
    year_col = 0
    if len(time_vector) > 0:
        col += 2
        year_col = col
        for t_val in time_vector:
            excel_page.write(row, col, t_val, formats[ExcelSettings.FORMAT_KEY_CENTER_BOLD])
            col += 1

    # Flesh out the contents.
    for item_number in range(num_items):
        col = start_col
        row += 1
        if quantity_types is not None:
            quantity_content = quantity_types[0]
            if condition_list[item_number] is not None:
                quantity_content = "=IF({0},{1},{2})".format(condition_list[item_number], "\"" + quantity_content + "\"", "\"\"")
                excel_page.write(row, col, quantity_content, None, quantity_types[0])
            else:
                excel_page.write(row, col, quantity_types[0])
            excel_page.data_validation(xlrc(row, col),
                                       {"validate": "list", "source": quantity_types})
            col += 1
        if len(time_vector) > 0:
            rc_start = xlrc(row, year_col)
            rc_end = xlrc(row, year_col + len(time_vector) - 1)
            def_content = "=IF(SUMPRODUCT(--({0}:{1}<>\"{2}\"))=0,{3},\"{4}\")".format(rc_start, rc_end, str(),
                                                                                       default_values[item_number],
                                                                                       SS.DEFAULT_SYMBOL_INAPPLICABLE)
            or_content = SS.DEFAULT_SYMBOL_OR
            if condition_list[item_number] is not None:
                def_content = "=IF({0},{1},{2})".format(condition_list[item_number], def_content.lstrip("="), "\"\"")
                or_content = "=IF({0},{1},{2})".format(condition_list[item_number], "\"" + or_content + "\"", "\"\"")
                excel_page.write(row, col + 1, or_content, formats[ExcelSettings.FORMAT_KEY_CENTER],
                                 SS.DEFAULT_SYMBOL_OR)
            else:
                excel_page.write(row, col + 1, or_content, formats[ExcelSettings.FORMAT_KEY_CENTER])
            excel_page.write(row, col, def_content, None, default_values[item_number])
        else:
            def_content = default_values[item_number]
            if condition_list[item_number] is not None:
                def_content = "=IF({0},{1},{2})".format(condition_list[item_number], def_content, "\"\"")
                excel_page.write(row, col, def_content, None, default_values[item_number])
            else:
                excel_page.write(row, col, def_content)

    last_row, last_col = row, start_col + 1 + len(time_vector)
    return last_row, last_col


# Utility functions for reading.

@accepts(xlrd.sheet.Sheet)
@returns(dict)
def extract_header_columns_mapping(excel_page, row=0):
    """
    Returns a dictionary mapping column headers in an Excel page to the column numbers in which they are found.
    The columns must be contiguous and are returned as a two-element list of first and last column.
    """
    header_columns_map = dict()
    current_header = None
    for col in range(excel_page.ncols):
        header = str(excel_page.cell_value(row, col))
        if not header == "":
            if header not in header_columns_map:
                header_columns_map[header] = [col, col]
            elif not current_header == header:
                error_message = "An Excel file page contains multiple headers called '{0}'.".format(header)
                logger.error(error_message)
                raise AtomicaException(error_message)
            current_header = header
        if current_header is not None:
            header_columns_map[current_header][-1] = col
    return header_columns_map


@accepts(xlrd.sheet.Sheet, int, int)
def extract_excel_sheet_value(excel_page, start_row, start_col, stop_row=None, stop_col=None, filters=None):
    """
    Returns a value extracted from an Excel page, but converted to type according to a list of filters.
    The value will be pulled from rows starting at 'start_row' and terminating before reading 'stop_row'.
    A similar restriction holds for columns.
    Note that 'stop_row' and its column equivalent is one further along than a 'last_row' and its equivalent.
    Empty-string values are always equivalent to a value of None being returned.
    """
    if filters is None:
        filters = []
    value, old_value = None, None
    row, col = start_row, start_col
    if stop_row is None:
        stop_row = row + 1
    if stop_col is None:
        stop_col = col + 1
    rc_start = xlrc(start_row, start_col)
    rc = rc_start
    # If columns without headers follow this column in the Excel page, scan through them.
    # Ditto with rows without item names that follow this row in the Excel page.
    while row < stop_row:
        while col < stop_col:
            value = str(excel_page.cell_value(row, col))
            if value == "":
                value = None
            elif ExcelSettings.FILTER_KEY_LIST in filters:
                value = [item.strip() for item in value.strip().split(ExcelSettings.LIST_SEPARATOR)]

            if old_value is not None:  # If there is an old value, this is not the first important cell examined.
                if value is None:
                    value = old_value  # If the new value is not important, maintain the old value.
                else:
                    # Expand lists with additional cell contents if appropriate.
                    if ExcelSettings.FILTER_KEY_LIST in filters:
                        value = old_value + value
                    # Otherwise, ignore with a warning.
                    else:
                        rc = xlrc(row, col)
                        logger.warning("Value '{0}' at cell '{1}' on page '{2}' is still considered part of the item "
                                       "and specification (i.e. header) located at cell '{3}'. It will be "
                                       "ignored for the previous value of '{4}'.".format(value, rc, excel_page.name,
                                                                                         rc_start, old_value))
                        value = old_value
            old_value = value
            col += 1
        col = start_col
        row += 1

    # Convert to boolean values if specified by filter.
    # Empty strings and unidentified symbols are considered default values.
    if ExcelSettings.FILTER_KEY_BOOLEAN_YES in filters:
        if value == SS.DEFAULT_SYMBOL_YES:
            value = True
        else:
            if value not in [SS.DEFAULT_SYMBOL_NO, ""]:
                logger.warning("Did not recognize symbol on page '{0}', at cell '{1}'. "
                               "Assuming a default of '{2}'.".format(excel_page.name, rc, SS.DEFAULT_SYMBOL_NO))
            value = ""
    if ExcelSettings.FILTER_KEY_BOOLEAN_NO in filters:
        if value == SS.DEFAULT_SYMBOL_NO:
            value = False
        else:
            if value not in [SS.DEFAULT_SYMBOL_YES, ""]:
                logger.warning("Did not recognize symbol on page '{0}', at cell '{1}'. "
                               "Assuming a default of '{2}'.".format(excel_page.name, rc, SS.DEFAULT_SYMBOL_YES))
            value = ""
    if value == "":
        value = None
    return value
