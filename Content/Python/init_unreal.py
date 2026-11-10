# Copyright XUSJTUER. All Rights Reserved.

import unreal

from fabtoolset import toolsets
from fabtoolset import tests

toolsets._registration.register()

tests._test_runner = unreal.PythonTestRunner.create(
    'AI.Toolsets.FabToolset',
    unreal.PythonTestRunnerSearchOptions(root_module=tests.__name__))
