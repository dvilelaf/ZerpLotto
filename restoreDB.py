import Lotto
import json

testing = True

# Load configuration
configFilePath = 'configTest.json' if testing else 'config.json'

with open(configFilePath, 'r') as configFile:

    config = json.load(configFile) # TODO: validate json scheme

    lotto = Lotto.Lotto(config)

    lotto.rebuildDBfromLedger()