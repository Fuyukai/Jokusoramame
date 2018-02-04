"""
Lua evaluation engine plugin.
"""
import lupa


class LuaEvalEngine(object):
    """
    Represents a lua evaluation engine.
    """
    def __init__(self):
        #: The LuaRuntime used for the
        self.runtime = lupa.LuaRuntime()
