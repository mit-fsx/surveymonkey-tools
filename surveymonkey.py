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
    def __init__(self, dct_or_struct):
        if isinstance(dct_or_struct, Struct):
            self.__dict__.update(dct_or_struct.__dict__)
        else:
            self.__dict__.update(dct_or_struct)

    def _repr_contents(self):
        return u','.join(self.__dict__.keys())

    def __repr__(self):
        return "{0}({1})".format(self.__class__.__name__,
                                 self._repr_contents())

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
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.pages = [SurveyPage(p) for p in self.pages]

    def get_title(self):
        return self.title.text
        
class SurveyPage(Struct):
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.questions = [SurveyQuestion(q) for q in self.questions]
        self._question_idx = {q.question_id: q for q in self.questions}
    
    def get_question_by_id(self, q_id):
        if q_id in self._question_idx:
            return self._question_idx[q_id]
        raise ValueError('No question with id {0}'.format(q_id))

class SurveyQuestion(Struct):
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.type = SurveyQuestionType(self.type)
        self.answers = [SurveyAnswer(a) for a in self.answers]
        self._answer_idx = {a.answer_id: a for a in self.answers}

    def __contains__(self, answer_id):
        return answer_id in self._answer_idx

    def __getitem__(self, answer_id):
        return self._answer_idx[answer_id]

class SurveyQuestionType(Struct):
    def _repr_contents(self):
        return "{0}/{1}".format(self.family, self.subtype)

class SurveyAnswer(Struct):
    pass
#    def __init__(self, *args):
#        Struct.__init__(self, *args)
#        if not hasattr(self,'position'):
#            print self.__dict__
#            sys.exit(0)

class SurveyResponse(Struct):
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.questions = [SurveyQuestionResponse(q) for q in self.questions]
        self._question_idx = {q.question_id: q for q in self.questions}

    def get_response_for_question(self, question):
        assert isinstance(question, SurveyQuestion)
        if question.question_id not in self._question_idx:
            return ["(no repsonse)"]
        return self._question_idx[question.question_id].get(question)

class SurveyQuestionResponse(Struct):
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self._answer_idx = {a.row: a for a in self.answers if a.row != '0'}

    def __getitem__(self, row):
        return self._answer_idx[row].text if row in self._answer_idx else None

    def get(self, question):
        rv = []
        if question.type.family == 'open_ended':
            if question.type.subtype == 'multi':
                for subanswer in sorted(question.answers,
                                        key=lambda x: x.position):
                    rv.append((subanswer.text,
                              self[subanswer.answer_id]))
            elif question.type.subtype in ('essay', 'single'):
                assert len(self.answers) == 1
                assert self.answers[0].row == '0'
                rv.append(self.answers[0].text)
            else:
                raise Exception('Unformattable answer')
        else:
            for ans in self.answers:
                answer = question[ans.row]
                if answer.type == 'other':
                    rv.append("{0}: {1}".format(answer.text, ans.text))
                elif answer.type == 'row':
                    rv.append(answer.text)
                else:
                    raise Exception('Unformattable answer')
        return rv

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
            response_json = response.json(object_hook=Struct)
        except JSONDecodeError as e:
            logger.exception("Unable to decode response as JSON")
            logger.error("Response was: %s", response)
            raise SurveyMonkeyError('Could not read response')
        try:
            status = response_json.status
        except AttributeError:
            raise SurveyMonkeyError("JSON did not contain 'status'!")
        if status != 0:
            raise SurveyMonkeyError(self._status_codes[response_json['status']])
        return response_json.data

    def get_survey_questions(self, survey_id):
        details = self.make_request('get_survey_details',
                                    {'survey_id': survey_id})
        return SurveyDetails(details)

    def get_survey_responses(self, survey_id, *respondents):
        postdata = {'survey_id': survey_id,
                    'respondent_ids' : respondents}
        return {r.respondent_id: SurveyResponse(r) for r in self.make_request('get_responses', postdata)}

foo = Config.load()
sm = SurveyMonkey(foo.get_token(),
                  foo.app.api_key,
                  foo.api.base)

response = sm.get_survey_responses('20816427', '2799054163').values()[0]

for i in sm.get_survey_questions('20816427').pages[0].questions:
    print i.heading
    print "\n".join([repr(x) for x in response.get_response_for_question(i)])
    print "---"

