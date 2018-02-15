# The global user-agent
import sys

version = '.'.join(map(str, sys.version[0:2]))
USER_AGENT = "Mozilla/5.0 (compatible; Jokusoramame/v2; https://github.com/SunDwarf/Jokusoramame)" \
             " Python/{} (KHTML, like Gecko)".format(version)
