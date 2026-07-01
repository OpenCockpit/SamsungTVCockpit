from os import path
from Tools.Directories import resolveFilename, SCOPE_CONFIG


CONFIG_FOLDER = path.join(path.realpath(resolveFilename(SCOPE_CONFIG)), "SamsungTV")
TIMER_FILE = path.join(CONFIG_FOLDER, "Samsungtvplus.timer")
RESUMEPOINTS_FILE = path.join(CONFIG_FOLDER, "resumepoints.pkl")
PLUGIN_FOLDER = path.dirname(path.realpath(__file__))
PLUGIN_ICON = "plugin.png"
BOUQUET_FILE = "userbouquet.samsungtv_%s.tv"
BOUQUET_NAME = "Samsung TV Plus (%s)"
NUMBER_OF_LIVETV_BOUQUETS = 5
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
