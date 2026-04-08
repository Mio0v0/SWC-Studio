"""Public library API for swcstudio.

All interfaces (GUI, CLI, and external Python callers) should import these
functions or the corresponding tool/feature modules.
"""

from __future__ import annotations

from swcstudio.core.auto_typing import RuleBatchOptions
from swcstudio.plugins import (
    autoload_plugins_from_environment,
    get_plugin,
    list_all_feature_methods,
    list_feature_methods,
    list_plugins,
    load_plugin_module,
    load_plugins,
    register_method,
    register_plugin_manifest,
    register_plugin_method,
    unregister_method,
    unregister_plugin,
)
from swcstudio.tools.batch_processing.features.auto_typing import run_folder as batch_auto_typing
from swcstudio.tools.batch_processing.features.index_clean import run_folder as batch_index_clean_folder
from swcstudio.tools.batch_processing.features.simplification import (
    run_folder as batch_simplify_folder,
)
from swcstudio.tools.batch_processing.features.batch_validation import (
    validate_folder as batch_validate_folder,
)
from swcstudio.tools.batch_processing.features.radii_cleaning import (
    clean_folder as batch_radii_cleaning,
    clean_path as radii_clean_path,
)
from swcstudio.tools.batch_processing.features.swc_splitter import (
    split_folder as batch_split_folder,
)
from swcstudio.tools.morphology_editing.features.dendrogram_editing import (
    reassign_subtree_types,
    reassign_subtree_types_in_file,
)
from swcstudio.tools.morphology_editing.features.manual_label import (
    set_node_type_file as morphology_set_node_type_file,
    set_node_type_text as morphology_set_node_type_text,
)
from swcstudio.tools.morphology_editing.features.manual_radii import (
    set_node_radius_file as morphology_set_node_radius_file,
    set_node_radius_text as morphology_set_node_radius_text,
)
from swcstudio.tools.morphology_editing.features.simplification import (
    simplify_file as morphology_smart_decimation_file,
    simplify_swc_text as morphology_smart_decimation_text,
)
from swcstudio.tools.validation.features.auto_fix import auto_fix_file, auto_fix_text
from swcstudio.tools.validation.features.index_clean import (
    index_clean_file as validation_index_clean_file,
    index_clean_text as validation_index_clean_text,
)
from swcstudio.tools.validation.features.auto_typing import (
    auto_label_file as validation_auto_label_file,
    run_file as validation_auto_typing_file,
)
from swcstudio.tools.validation.features.run_checks import (
    validate_file as validation_run_file,
    validate_text as validation_run_text,
)
from swcstudio.tools.visualization.features.mesh_editing import (
    build_mesh_from_file,
    build_mesh_from_text,
)
from swcstudio.core.geometry_editing import (
    disconnect_branch as geometry_disconnect_branch,
    delete_node as geometry_delete_node,
    delete_subtree as geometry_delete_subtree,
    insert_node_between as geometry_insert_node_between,
    move_node_absolute as geometry_move_node_absolute,
    move_subtree_absolute as geometry_move_subtree_absolute,
    reconnect_branch as geometry_reconnect_branch,
    reindex_dataframe_with_map as geometry_reindex_dataframe_with_map,
)

__all__ = [
    "RuleBatchOptions",
    "batch_validate_folder",
    "batch_split_folder",
    "batch_auto_typing",
    "batch_simplify_folder",
    "batch_index_clean_folder",
    "batch_radii_cleaning",
    "radii_clean_path",
    "auto_fix_text",
    "auto_fix_file",
    "validation_index_clean_text",
    "validation_index_clean_file",
    "validation_auto_typing_file",
    "validation_run_text",
    "validation_run_file",
    "build_mesh_from_text",
    "build_mesh_from_file",
    "reassign_subtree_types",
    "reassign_subtree_types_in_file",
    "morphology_set_node_type_text",
    "morphology_set_node_type_file",
    "morphology_set_node_radius_text",
    "morphology_set_node_radius_file",
    "validation_auto_label_file",
    "morphology_smart_decimation_text",
    "morphology_smart_decimation_file",
    "geometry_move_node_absolute",
    "geometry_move_subtree_absolute",
    "geometry_reconnect_branch",
    "geometry_disconnect_branch",
    "geometry_delete_node",
    "geometry_delete_subtree",
    "geometry_insert_node_between",
    "geometry_reindex_dataframe_with_map",
    "load_plugin_module",
    "load_plugins",
    "autoload_plugins_from_environment",
    "register_plugin_manifest",
    "register_plugin_method",
    "unregister_plugin",
    "list_plugins",
    "get_plugin",
    "register_method",
    "unregister_method",
    "list_feature_methods",
    "list_all_feature_methods",
]
