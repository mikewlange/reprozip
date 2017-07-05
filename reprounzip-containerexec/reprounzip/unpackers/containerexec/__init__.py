# prepare for Python 3
from __future__ import absolute_import, division, print_function, unicode_literals

try:  # pragma: no cover
    __import__('pkg_resources').declare_namespace(__name__)
except ImportError:  # pragma: no cover
    from pkgutil import extend_path
    __path__ = extend_path(__path__, __name__)

__version__ = '0.1'

class BenchExecException(Exception):
    pass