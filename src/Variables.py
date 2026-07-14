import os
from Tools.Directories import resolveFilename, SCOPE_CONFIG
from .Version import PLUGIN


CONFIG_FOLDER = os.path.join(os.path.realpath(resolveFilename(SCOPE_CONFIG)), PLUGIN)
TIMER_FILE = os.path.join(CONFIG_FOLDER, PLUGIN + ".timer")
RESUMEPOINTS_FILE = os.path.join(CONFIG_FOLDER, "resumepoints.pkl")
PLUGIN_FOLDER = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ICON = "plugin.png"
BOUQUET_FILE = "userbouquet.samsungtvcockpit_%s.tv"
BOUQUET_NAME = "Samsung TV Cockpit (%s)"
NUMBER_OF_LIVETV_BOUQUETS = 5
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
