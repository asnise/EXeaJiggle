bl_info = {
    "name": "EXea Jiggle",
    "author": "Axnise",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > EXea Jiggle",
    "description": "Effortless real-time jiggle bone physics and secondary motion",
    "category": "Animation",
    "doc_url": "https://github.com/asnise/EXeaJiggle",
    "tracker_url": "https://github.com/asnise/EXeaJiggle/issues",
}

if "bpy" in locals():
    import importlib
    importlib.reload(core)
    importlib.reload(operators)
    importlib.reload(ui)
else:
    from . import core
    from . import operators
    from . import ui

import bpy


def register():
    core.register()
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
    core.unregister()
