"""
Python module for surveymonkey API
"""

import json
import logging
import sys
import time
import re

from distutils.version import StrictVersion
from simplejson.decoder import JSONDecodeError
from xml.sax import saxutils

import requests

logger = logging.getLogger('surveymonkey')

class ConfigError(Exception):
    pass

class SurveyMonkeyError(Exception):
    pass

class Struct:
    def __init__(self, dct):
        self.__dict__.update(dct)

class Config(Struct):
    """
    For convenience.
    """
    CONFIG_FILE="/afs/athena.mit.edu/astaff/project/helpdesk" \
        "/web_scripts/surveymonkey/private/config.json"

    def get_token(self):
        token = None
        try:
            with open(self.token_file, 'r') as f:
                token = f.read()
        except IOError as e:
            raise ConfigError("{0} while reading token".format(e))
        except AttributeError as e:
            raise ConfigError("No token_file value in config file.")
        return token
    
    @staticmethod
    def load(filename=None):
        if filename is None:
            filename = Config.CONFIG_FILE
        with open(filename, 'r') as f:
            obj = json.loads(f.read(),
                             object_hook=Config)
        return obj
        
class SurveyDetails(Struct):
    def __init__(self, dct):
        Struct.__init__(self, dct)



class SurveyMonkey:
    _status_codes = ('Success',
                     'Not Authenticated',
                     'Invalid User Credentials',
                     'Invalid Request',
                     'Unknown User',
                     'System Error')

    def __init__(self, token, api_key, base_uri):
        if StrictVersion(requests.__version__) < StrictVersion('1.1.0'):
            raise SurveyMonkeyError("'requests' library too old; version 1.1.0 or higher required")
        assert token is not None
        assert api_key is not None
        assert base_uri is not None
        self.base_uri = base_uri
        self.client = requests.session()
        self.client.headers = {
            "Authorization": "bearer {0}".format(token),
            "Content-Type": "application/json"
            }
        # The api_key must be passed as a param, because it's part
        # of the URL being POSTed to.  It cannot be in the POST data.
        self.client.params = {
            "api_key": api_key
            }
        
    def make_request(self, method, data):
        url = "{0}/v2/surveys/{1}".format(self.base_uri, method)
        logger.debug("Making request to %s, data=%s", url, str(data))
        response = self.client.post(url, data=json.dumps(data))
        # TODO: Better avoidance of rate limiting
        time.sleep(0.3)
        try:
            response_json = response.json()
        except JSONDecodeError as e:
            logger.exception("Unable to decode response as JSON")
            logger.error("Response was: %s", response)
            raise SurveyMonkeyError('Could not read response')
        if 'status' not in response_json:
            raise SurveyMonkeyError("JSON did not contain 'status'!")
        if response_json['status'] != 0:
            raise SurveyMonkeyError(self._status_codes[response_json['status']])
        return response_json['data']

    def get_survey_questions(self, survey_id):
        details = self.make_request('get_survey_details',
                                    {'survey_id': survey_id})
        return json.loads(json.dumps(details),
                          object_hook=SurveyDetails)

foo = Config.load()
sm = SurveyMonkey(foo.get_token(),
                  foo.app.api_key,
                  foo.api.base)
print sm.get_survey_questions('20816427').__dict__
