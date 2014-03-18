#!/usr/bin/python

import sys
import os
import time
from distutils.version import StrictVersion
import requests

if StrictVersion(requests.__version__) < StrictVersion('1.1.0'):
    print >>sys.stderr, "Version 1.1.0 of the 'requests' library is required."
    print >>sys.stderr, "For convenience, there is a copy in /mit/helpdesk/src"
    sys.exit(1)
import json
import logging
import subprocess

CONFIG_FILE="/afs/athena.mit.edu/astaff/project/helpdesk" \
    "/web_scripts/surveymonkey/private/config.json"
STATE_FILE="/afs/athena.mit.edu/astaff/project/helpdesk" \
    "/cron_scripts/poll.state"
LOG_FILE="debug.log"

# Survey title
SURVEY_TITLE="Student Application and Technical Survey"

logger = logging.getLogger('grader')
#debug_handler = logging.FileHandler(LOG_FILE)
debug_handler = logging.StreamHandler()
logger.setLevel(logging.DEBUG)
logger.addHandler(debug_handler)

# Load the config file
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.loads(f.read())
except (ValueError, IOError) as e:
    logger.exception("Exception while reading config file")
    sys.exit(0)

def make_request(client, method, data):
    url = "{0}/v2/surveys/{1}".format(config['api']['base'],
                                      method)
    logger.debug("Making request to %s, data=%s", url, str(data))
    response = client.post(url, data=json.dumps(data))
    # TODO: Better avoidance of rate limiting
    time.sleep(0.3)
    try:
        response_json = response.json()
    except JSONDecodeError as e:
        logger.exception("Unable to decode response as JSON")
        logger.error("Response was: %s", response)
        sys.exit(1)
    if response_json['status'] != 0:
        logger.error("Request returned API status: %s", 
                     response_json['status'])
        sys.exit(1)
    return response_json['data']

def get_survey_questions(client, survey_id):
    details = make_request(client, 'get_survey_details',
                           {'survey_id': survey_id})
    return (details['title']['text'], details['pages'])

def get_survey_responses(client, survey_id, respondent_id):
    postdata = {'survey_id': survey_id,
                'respondent_ids' : [respondent_id]}
    responses = make_request(client, 'get_responses', postdata)
    return {x['question_id']: x['answers'] for x in responses[0]['questions']}

def get_survey_id(client, title):
    postdata = { 'title': title }
    survey_list = make_request(client, 'get_survey_list', postdata)
    surveys = survey_list['data']['surveys']
    assert len(surveys) < 2, "Multiple surveys returned!"
    if len(surveys) < 1:
        logger.debug("No surveys found.")
        return None
    return surveys[0]['survey_id']

def get_respondents(client, survey_id, date):
    postdata = {'survey_id': survey_id,
                'fields': ['date_modified', 'status'],
                'start_modified_date': date}
    respondents = make_request(client, 'get_respondent_list', postdata)
    return respondents['data']['respondents']

# __main__

try:
    with open(config['token_file'], 'r') as f:
        token = f.read()
except (IOError, KeyError) as e:
    logger.exception("Failed to read token file")
    sys.exit(1)

client = requests.session()
client.headers = {
    "Authorization": "bearer {0}".format(token),
    "Content-Type": "application/json"
    }
client.params = {
    "api_key": config['app']['api_key']
}

survey_id='20816427'
respondent_id='3122352155'
respondent_id='2803655571'
respondent_id='2799054163'

(title, pages) = get_survey_questions(client, survey_id)
responses = get_survey_responses(client, survey_id, respondent_id)

# print
print title
for page in pages:
    # Skip pages with no questions (e.g. informational)
    if len(page['questions']) == 0:
        continue
    # Whee, Unicode
    print page['heading'].center(72)
    # Should already be sorted, but...
    # 'presentation' questions have no response
    for q in sorted([x for x in page['questions'] if x['type']['family'] != 'presentation'], key=lambda x: x['position']):
        print u"{0}".format(q['heading'])
        if q['question_id'] not in responses:
            print "(no response)"
        else:
            for answer in responses[q['question_id']]:
                assert u'row' in answer
                # row=0 for single freeform answers
                text = answer.get(u'text', None)
                result = text
                if answer['row'] != u'0':
                    rows = [a for a in q['answers'] if a['answer_id'] == answer['row']]
                    assert len(rows) == 1
                    if rows[0]['type'] == 'other':
                        result = '{0}: {1}'.format(rows[0]['text'],
                                                   text)
                    elif text is not None:
                        result = u" {0}\n    {1}".format(rows[0]['text'],
                                                         text)
                    else:
                        result = rows[0]['text']
                print result
            
        print "---------------------------"
