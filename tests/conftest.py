import sys
import types


class _FakeNodeType:
    VISUALIZER = "Visualizer"


class _Param:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _identity_decorator(*args, **kwargs):
    def wrap(cls):
        return cls

    return wrap


def _install_stub():
    sys.modules.pop("knime", None)
    sys.modules.pop("knime.extension", None)

    knime = types.ModuleType("knime")
    ext = types.ModuleType("knime.extension")

    ext.category = lambda *args, **kwargs: "/community/pdf_tools"
    ext.node = _identity_decorator
    ext.output_view = _identity_decorator
    ext.input_table = _identity_decorator
    ext.output_table = _identity_decorator
    ext.parameter_group = _identity_decorator
    ext.NodeType = _FakeNodeType
    ext.StringParameter = _Param
    ext.IntParameter = _Param
    ext.DoubleParameter = _Param
    ext.BoolParameter = _Param
    ext.view_html = staticmethod(lambda html: ("view_html", html))

    knime.extension = ext
    sys.modules["knime"] = knime
    sys.modules["knime.extension"] = ext


_install_stub()
