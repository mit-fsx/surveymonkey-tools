"""
Python module for surveymonkey API
"""
import sys
if sys.hexversion < 0x2060000:
    raise Exception("Python 2.6 required")

import json
import logging
import time
import re

from distutils.version import StrictVersion
from simplejson.decoder import JSONDecodeError
from xml.sax import saxutils

import requests

logger = logging.getLogger('surveymonkey')

class SurveyMonkeyError(Exception):
    pass

class Struct:
    """
    Simple object-like storage for dictionaries.  Can be constructed
    from a dict or another Struct().
    """
    def __init__(self, from_obj):
        if not isinstance(from_obj, (Struct, dict)):
            raise TypeError("Struct() takes a dict or another Struct")
        if isinstance(from_obj, Struct):
            from_obj = from_obj.__dict__
        self.__dict__.update(from_obj)

    def __repr__(self):
        return "{0}({1})".format(self.__class__.__name__,
                                 repr(self.__dict__))

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
            raise SurveyMonkeyError("{0} while reading token".format(e))
        except AttributeError as e:
            raise SurveyMonkeyError("No token_file value in config file.")
        return token

    @staticmethod
    def load(filename=None):
        if filename is None:
            filename = Config.CONFIG_FILE
        with open(filename, 'r') as f:
            obj = json.loads(f.read(),
                             object_hook=Config)
        return obj

class SurveyList(Struct):
    """A list of surveys
    
    Supports iteration, access by index, and len()
    """
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.surveys = [SurveyInfo(s) for s in self.surveys]
        self.pages=[self.page]

    def __getitem__(self, key):
        return self.surveys[key]

    def __len__(self):
        return len(self.surveys)

    def __iter__(self):
        return iter(self.surveys)

    def add_page(self, page):
        self.surveys += [SurveyInfo(s) for s in page.surveys]
        self.pages.append(page.page)

class RespondentList(Struct):
    """A list of respondents
    
    Supports iteration, access by index, and len()
    """
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.respondents = [RespondentInfo(r) for r in self.respondents]
        self.pages=[self.page]

    def __getitem__(self, key):
        return self.respondents[key]

    def __len__(self):
        return len(self.respondents)

    def __iter__(self):
        return iter(self.respondents)

    def add_page(self, page):
        self.respondents += [RespondentInfo(r) for r in page.respondents]
        self.pages.append(page.page)

class RespondentInfo(Struct):
    """Holds information for a single respondent.

    The name and other metadata fields are not populated for web
    collectors.
    """
    _fields = ('date_start', 'date_modified', 'collector_id',
               'collection_mode', 'custom_id', 'email', 'first_name',
               'last_name', 'ip_address', 'status', 'analysis_url')

    def __init__(self, *args):
        Struct.__init__(self, *args)

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name in self._fields:
            raise SurveyMonkeyError('{0} field not initialized.'.format(name))
        else:
            raise AttributeError(
                "RespondentInfo instance has no attribute '{0}'".format(name))

class SurveyInfo(Struct):
    """Holds info for a single respondent.
    """
    _fields = ('title', 'analysis_url', 'date_created', 'date_modified',
               'language_id', 'question_count', 'num_responses')

    def __init__(self, *args):
        Struct.__init__(self, *args)

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name in self._fields:
            raise SurveyMonkeyError('{0} field not initialized.'.format(name))
        else:
            raise AttributeError(
                "SurveyInfo instance has no attribute '{0}'".format(name))

    def get_title(self):
        """Return the title of a survey."""
        # self.title can be a Struct (for SurveyDetails) or just a string
        if isinstance(self.title, Struct):
            return self.title.text
        else:
            return self.title

class SurveyDetails(SurveyInfo):
    """Holds survey "details", including pages and questions.
    """
    def __init__(self, *args):
        SurveyInfo.__init__(self, *args)
        self.pages = [SurveyPage(p) for p in self.pages]

    def get_questions_by_heading(self, *headings):
        """Given one or more headings, return a list of SurveyQuestions
        The list will be in the same order as in the caller.  List items
        will either be a SurveyQuestion, or None if the question could not
        be found.

        Raises SurveyMonkeyError if multiple questions are found with
        the same heading.
        """
        rv = []
        for h in headings:
            questions = [q for q in
                         [p.get_question_by_heading(h) for p in self.pages]
                         if q is not None]
            if len(questions) > 1:
                raise SurveyMonkeyError(
                    'Multiple questions found for {0}'.format(h))
            try:
                rv.append(questions.pop())
            except IndexError:
                rv.append(None)
        return rv

class SurveyPage(Struct):
    """
    A page of the survey.

    Supports iteration over all answerable (i.e. questions that are
    not images or descriptive text) questions.  For all questions,
    iterate over .questions.  Supports len(), as well as tests for
    membership and accessing by question id.
    """
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.questions = [SurveyQuestion(q) for q in self.questions]
        self._question_idx = {q.question_id: q for q in self.questions}

    def __iter__(self):
        return iter([q for q in self.questions if q.answerable()])

    def __len__(self):
        return len(self.questions)

    def __contains__(self, question_id):
        return question_id in self._question_idx

    def __getitem__(self, question_id):
        return self._question_idx[question_id]

    def get_question_by_heading(self, heading):
        """Given a question heading, find the question in the page.

        Returns None if not found, SurveyQuestion if found.
        Raises SurveyMonkeyError if multiple questions with same
        heading are found.
        """
        questions = [q for q in self.questions if q.heading == heading]
        if len(questions) > 1:
            raise SurveyMonkeyError(
                'Multiple questions found for {0}'.format(heading))
        if len(questions) == 0:
            return None
        return questions[0]

class SurveyQuestion(Struct):
    """A question on the survey.

    Performs some basic validation on the answers attribute.  Supports
    membership tests and key access by answer_id.
    """
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.type = SurveyQuestionType(self.type)
        self.answers = [SurveyAnswer(a) for a in self.answers]
        self._answer_idx = {a.answer_id: a for a in self.answers}
        # Because we require this in ParsedQuestionResponse when sorting
        if self.type == "open_ended/multi":
            if not all([hasattr(x, 'position') for x in self.answers]):
                raise SurveyMonkeyError(
                    "Unexpected set of answers for question {0}".format(
                        self.question_id))

    def __repr__(self):
        return "SurveyQuestion(#{0},{1},id={2})\n  {3}{4}".format(
            self.position,
            self.type,
            self.question_id,
            '(no answers)' if len(self.answers) == 0 else '',
            '\n  '.join([repr(x) for x in self.answers]))

    def __contains__(self, answer_id):
        return answer_id in self._answer_idx

    def __getitem__(self, answer_id):
        return self._answer_idx[answer_id]

    def answerable(self):
        return self.type.family != 'presentation'

class SurveyQuestionType(Struct):
    """
    A 'type' of question, consisting of a family and subtype.
    Supports comparison with other SurveyQuestionTypes, or with
    a string in the format: "family/subtype".
    """
    def __cmp__(self, other):
        if not isinstance(other, (str, SurveyQuestionType)):
            raise TypeError("Cannot compare with {0}".format(type(other)))
        return cmp(repr(other), repr(self))

    def __repr__(self):
        return "'{0}/{1}'".format(self.family, self.subtype)

class SurveyAnswer(Struct):
    """An answer to a question on the survey.

    This is not a response to a question, it is one of any possible
    answers to the question.  Not all questions have answers.
    """
    def __repr__(self):
        return "SurveyAnswer({0}{1},{2},{3},\"{4}\",{5})".format(
            '#{0}'.format(self.__dict__.get('position', None)),
            '(hidden)' if not self.visible else '',
            self.answer_id,
            self.type,
            self.text,
            [str(x) for x in self.__dict__.keys() if x not in ('answer_id',
                                                               'type',
                                                               'text',
                                                               'visible',
                                                               'position',
                                                               )])

class SurveyResponse(Struct):
    """A response to a survey.
    
    Contains responses to questions.  Supports accessing by question_id,
    but returns None rather than raising IndexError or KeyError.
    """
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self.questions = [SurveyQuestionResponse(q) for q in self.questions]
        self._question_idx = {q.question_id: q for q in self.questions}

    def __getitem__(self, question_id):
        if question_id in self._question_idx:
            return self._question_idx[question_id]
        return None

    def get_response_for_question(self, question):
        return ParsedQuestionResponse(question,
                                      self[question.question_id])

class SurveyQuestionResponse(Struct):
    """A response to an individual question on a survey

    Supports accessing the value for a a specific answer_id by
    key, returning None if not found.
    """
    def __init__(self, *args):
        Struct.__init__(self, *args)
        self._answer_idx = {a.row: a for a in self.answers if a.row != '0'}

    def __getitem__(self, row):
        assert row != '0'
        return self._answer_idx[row].text if row in self._answer_idx else None

    def __repr__(self):
        return "SurveyQuestionResponse(q_id={0}, {1} answers)\n  {2}".format(
            self.question_id,
            len(self.answers),
            '\n  '.join([repr(x) for x in self.answers]))

class ParsedQuestionResponse:
    """A parsed response to a question, suitable for formatting.

    question is always required and is a SurveyQuestion.
    response may be None, which indicates no answer was provided.
    
    The boolean value of the answer indicates whether any sort of
    response was given or not.

    Some knowledge of the type is required by the formatter.
    Attributes:
    - answer: The response, if the question is not a multiple-answer question.
              None, a value, or a list of values.
    - subquestions: The prompts and responses for the "sub questions",
                    if a multi-answer question
    - other: If the question had an 'other' answer, and a response was given,
             this is a tuple of (answer, response) where 'answer' is the
             text of the 'Other' answer
    - type: The SurveyQuestionType of the question.
    """
    def __init__(self, question, response):
        if not isinstance(question, SurveyQuestion):
            raise TypeError("SurveyQuestion required")
        self._question = question
        self._response = response
        self.heading = question.heading
        self.position = question.position
        self.answer = []
        self.type = question.type
        if response is not None:
            self._parse_response()

    def __nonzero__(self):
        return len(self.answer) > 0

    def _parse_response(self):
        if self.type.family == 'presentation':
            # Nothing to do for these
            return
        if self.type.family == 'open_ended':
            if self.type.subtype in ('multi','numerical'):
               # open_ended/multi questions have "sub questions"
               # e.g. a), b), c)
               # This should already be sorted, but we'll do it anyway
                for subanswer in sorted(self._question.answers,
                                        key=lambda x: x.position):
                    # Append a tuple of the subanswer text, and the response for
                    # that answer_id (which may be None
                    self.answer.append(
                        (subanswer.text, self._response[subanswer.answer_id]))
            elif self.type.subtype in ('essay', 'single'):
                if len(self._response.answers) > 1:
                    raise SurveyMonkeyError("Found multiple answers for "
                                            "single response answer.")
                if self._response.answers[0].row != '0':
                    raise SurveyMonkeyError("Found single response with "
                                            "non-zero row.")
                self.answer.append(self._response.answers[0].text)
            else:
                raise SurveyMonkeyException(
                    "Unknown open_ended subtype {0} question id {1}".format(
                        self.type.subtype, self._question.question_id))
        elif self.type.family in ('single_choice', 'multiple_choice'):
            other = None
            for ans in self._response.answers:
                # Each response here should have a 'row', and possibly
                # a 'text' attribute.  We must match the row with
                # that answer_id in the question to find out what the
                # text of that choice was.
                answer = self._question[ans.row]
                if answer.type == 'other':
                    # Save to append at end
                    other = (answer.text, ans.text)
                elif answer.type == 'row':
                    self.answer.append(answer.text)
                else:
                    raise SurveyMonkeyException(
                        "Unknown answer type {0} for question id {1})".format(
                            self.type, self._question.question_id))
            if other is not None:
                self.answer.append(other)
        elif self.type.family in ('matrix'):
            for ans in self._response.answers:
                # TODO: weight?
                self.answer.append((self._question[ans.row].text,
                                    self._question[ans.col].text))
        else:
            raise SurveyMonkeyException(
                "Can't parse {0} question id {1}".format(
                    self.type, self._question.question_id))

    def __repr__(self):
        rv = u"ParsedQuestionResponse({0}, {1}\n  {2}".format(
            self.type, self.heading, self.answer)
        return rv.encode("utf-8")

class SurveyMonkey:
    """
    The connection to SurveyMonkey
    """
    _status_codes = ('Success',
                     'Not Authenticated',
                     'Invalid User Credentials',
                     'Invalid Request',
                     'Unknown User',
                     'System Error')

    _default_base_uri = 'https://api.surveymonkey.net'
    def __init__(self, token, api_key, **kwargs):
        if StrictVersion(requests.__version__) < StrictVersion('1.1.0'):
            raise SurveyMonkeyError("'requests' library too old;"
                                    "version 1.1.0 or higher required")
        
        if token is None:
            raise ValueError("token required")
        if api_key is None:
            raise ValueError("api_key required")
        self.base_uri = kwargs.get('base_uri', self._default_base_uri)
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

    def _make_request(self, method_name, data=None):
        try:
            prefix, method = method_name.split('.', 1)
        except ValueError:
            raise ValueError("Can't parse method: {0}".format(method_name))
        url = "{0}/v2/{1}/{2}".format(self.base_uri, prefix, method)
        logger.debug("Making request to %s, data=%s", url, str(data))
        response = self.client.post(url, data=json.dumps(data))
        # TODO: Better avoidance of rate limiting
        time.sleep(0.4)
        if not response:
            raise SurveyMonkeyError('Bad response: ' + repr(response))
            logger.error("Response code: {0} text: {1}".format(
                    response.status_code, response.text))
            response.raise_for_status()
        try:
            # This is a hack until we can use requests version 1.2.0
            # everywhere, which supports kwargs in the json() method
            # e.g. response_json = response.json(object_hook=Struct)
            response_json = json.loads(json.dumps(response.json()),
                                       object_hook=Struct)
        except JSONDecodeError as e:
            logger.exception("Unable to decode response as JSON")
            logger.error("Response was: %s", response)
            raise SurveyMonkeyError('Could not read response')
        try:
            status = response_json.status
        except AttributeError:
            raise SurveyMonkeyError("JSON did not contain 'status'!")
        if status != 0:
            raise SurveyMonkeyError(self._status_codes[response_json.status])
        return response_json.data

    def get_survey_details(self, survey_id):
        """Get survey details for a survey_id"""
        details = self._make_request('surveys.get_survey_details',
                                     {'survey_id': survey_id})
        return SurveyDetails(details)

    def get_survey_responses(self, survey_id, *respondents):
        """Get responses to a survey, given one or more respondents"""
        if len(respondents) < 1:
            raise ValueError("One or more respondents required")
        postdata = {'survey_id': survey_id,
                    'respondent_ids' : respondents}
        return {r.respondent_id: SurveyResponse(r) for r in
                self._make_request('surveys.get_responses', postdata)}

    def get_survey_list(self, fields=SurveyInfo._fields, **kwargs):
        """Get a list of all surveys"""
        postdata={'fields': fields}
        for arg, val in [(k, kwargs.get(k, None)) for k in
                         'page_size', 'page',
                         'start_date', 'end_date', 'title',
                         'recipient_email', 'order_asc']:
            if val is not None:
                postdata[arg] = val
        max_pages=kwargs.get('max_pages', 0 if 'page' in postdata else 10)
        s_list = SurveyList(self._make_request('surveys.get_survey_list',
                                               postdata))
        for _ in xrange(max_pages - 1):
            postdata['page'] = s_list.pages[-1] + 1
            next_page = self._make_request('surveys.get_survey_list',
                                           postdata)
            if len(next_page.surveys) == 0:
                break
            s_list.add_page(next_page)
        return s_list

    def get_survey_respondents(self, survey_id,
                               fields=RespondentInfo._fields, **kwargs):
        """Get a list of respondents to a survey_id"""
        postdata={'survey_id': survey_id,
                  'fields': fields}
        for arg, val in [(k, kwargs.get(k, None)) for k in
                         'page_size', 'page',
                         'collector_id', 'start_date', 'end_date',
                         'start_modified_date', 'end_modified_date',
                         'order_by', 'order_asc']:
            if val is not None:
                postdata[arg] = val
        max_pages=kwargs.get('max_pages', 0 if 'page' in postdata else 10)
        r_list = RespondentList(
            self._make_request('surveys.get_respondent_list', postdata))
        for _ in xrange(max_pages - 1):
            postdata['page'] = r_list.pages[-1] + 1
            next_page = self._make_request('surveys.get_respondent_list',
                                           postdata)
            if len(next_page.respondents) == 0:
                break
            r_list.add_page(next_page)
        return r_list

    def get_user_details(self):
        return self._make_request('user.get_user_details').user_details
