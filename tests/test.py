# -*- coding: utf-8 -*-
"""
Optima Core framework test file.
Tests the creation, importing and exporting of model framework files.
"""

import unittest

from optimacore.project import Project

from optimacore.workbook_export import writeWorkbook
from optimacore.workbook_import import readWorkbook
from optimacore.system import SystemSettings as SS
from optimacore.structure_settings import FrameworkSettings as FS
from optimacore.structure_settings import DatabookSettings as DS

import sys
import pprint

class EverythingTest(unittest.TestCase):
    """  """
    
    def setUp(self):
        self.proj = Project()
        self.framework_template_filepath = "./frameworks/framework_template.xlsx"
        self.framework_example_filepath = "./frameworks/framework_example.xlsx"
        self.databook_empty_filepath = "./databooks/databook_empty.xlsx"
        self.databook_template_filepath = "./databooks/databook_template.xlsx"

    def tearDown(self):
        self.proj = None

    #def test_databook_empty_creation(self):
    #    """  """
    #    self.proj.createDatabook(databook_path = self.databook_empty_filepath)
    #    return None

    def test_workbook_process(self):
        """  """
        writeWorkbook(workbook_path = "./frameworks/framework_test.xlsx", framework = None, data = None, instructions = None, workbook_type = SS.STRUCTURE_KEY_FRAMEWORK)
        readWorkbook(workbook_path = "./frameworks/framework_ukraine.xlsx", framework = self.proj.framework, data = None, workbook_type = SS.STRUCTURE_KEY_FRAMEWORK)
        writeWorkbook(workbook_path = "./databooks/databook_ukraine.xlsx", framework = self.proj.framework, data = None, instructions = None, workbook_type = SS.STRUCTURE_KEY_DATA)
        readWorkbook(workbook_path = "./databooks/databook_ukraine.xlsx", framework = self.proj.framework, data = self.proj.data, workbook_type = SS.STRUCTURE_KEY_DATA)

#        writeWorkbook(workbook_path = "./frameworks/framework_test.xlsx", framework = None, data = None, instructions = None, workbook_type = SS.STRUCTURE_KEY_FRAMEWORK)
#        writeWorkbook(workbook_path = "./databooks/databook_ukraine.xlsx", framework = self.proj.framework, data = None, instructions = None, workbook_type = SS.STRUCTURE_KEY_DATA)
        #readWorkbook(workbook_path = "./ukraine_frameworks_test.xlsx", framework = self.proj.framework, data = None, workbook_type = SS.STRUCTURE_KEY_FRAMEWORK)
        #readWorkbook(workbook_path = "./ukraine_databook_test.xlsx", framework = self.proj.framework, data = self.proj.data, workbook_type = SS.STRUCTURE_KEY_DATA)

        print("-"*100)
        pprint.pprint(self.proj.framework.specs)
        print("-"*100)
        pprint.pprint(self.proj.data.specs)
        print("-"*100)
        #pprint.pprint(self.proj.framework.semantics)
        #print("-"*100)
        #pprint.pprint(self.proj.data.semantics)
        #print("-"*100)
        #pprint.pprint(DS.ITEM_TYPE_SPECS)
        return None
    
    #def test_framework_example_import(self):
    #    """  """
    #    self.proj.getFramework().importFromFile(framework_path = self.framework_example_filepath)
    #    return None
        
if __name__ == '__main__':
    unittest.main()