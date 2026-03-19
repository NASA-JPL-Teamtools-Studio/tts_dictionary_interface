# Helper file to support installing locally on older Python systems.
# Once we can move 100% to a system like pyproject.toml or poetry,
# we can ditch this file and setup_from_pyproject. But as long
# as we have missions on 3.6.4, we should keep it in place so
# we can dev locally on those projects and install this locally.
from tts_utilities.setup_from_pyproject import setup_from_pyproject

setup_from_pyproject()
