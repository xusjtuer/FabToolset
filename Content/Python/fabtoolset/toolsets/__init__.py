# Copyright XUSJTUER. All Rights Reserved.

from fabtoolset.toolsets.fab_catalog import FabCatalogTools
from fabtoolset.toolsets.fab_import import FabImportTools
from fabtoolset.toolsets.fab_library import FabLibraryTools
from fabtoolset.toolsets.local_library import FabLocalLibraryTools
from toolset_registry.registration import Registration

_registration = Registration([FabCatalogTools, FabImportTools, FabLibraryTools, FabLocalLibraryTools])
