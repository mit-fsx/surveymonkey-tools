"""
Python module for surveymonkey API
"""

import json

class ConfigError(Exception):
    pass

class Config:
    """
    For convenience.
    """
    CONFIG_FILE="/afs/athena.mit.edu/astaff/project/helpdesk" \
        "/web_scripts/surveymonkey/private/config.json"

    def __init__(self, dct):
        self.__dict__.update(dct)

    def get_token(self):
        token = None
        try:
            with open(self.token_file, 'r') as f:
                token = f.read()
        except IOError as e:
            raise ConfigError("{0} while reading token".format(e))
        except AttributeError as e:
            raise ConfigError("No token_file value in config file.")
    
    @staticmethod
    def load(filename=None):
        if filename is None:
            filename = Config.CONFIG_FILE
        with open(filename, 'r') as f:
            obj = json.loads(f.read(),
                             object_hook=lambda x: Config(x))
        return obj
        

class SurveyMonkey:
    def __init__(self, **kwargs):
        pass

foo = Config.load()
print foo.api.token_endpoint
print foo.api.base2
