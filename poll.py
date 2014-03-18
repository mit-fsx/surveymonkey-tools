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
LOG_FILE="/afs/athena.mit.edu/astaff/project/helpdesk" \
    "/cron_scripts/debug.log"

# What questions do we want
QUESTIONS=['Name:', 'MIT email address:']
# Survey title
SURVEY_TITLE="Student Application and Technical Survey"

logger = logging.getLogger('poll')
debug_handler = logging.FileHandler(LOG_FILE)
stderr_handler = logging.StreamHandler()
stderr_handler.setLevel(logging.WARNING)
logger.setLevel(logging.DEBUG)
logger.addHandler(debug_handler)
logger.addHandler(stderr_handler)

logger.debug("**BEGIN** at %s", time.strftime("%Y-%m-%d %H:%M"))
# Load the config file
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.loads(f.read())
except (ValueError, IOError) as e:
    logger.exception("Exception while reading config file")
    sys.exit(0)

def send_email(output):
    tmpl = """To: {0}
From: CS Hiring Survey Checker <devnull@mit.edu>
Subject: New Technical Surveys
"""
    sendmail = subprocess.Popen(['/usr/sbin/sendmail', '-t'],
                                stdin=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    (_, err) = sendmail.communicate(tmpl.format(config['email_to']) + output)
    if sendmail.returncode != 0:
        logger.error("Failed to send mail: %s", err)
        sys.exit(1)

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
    return response_json

def get_survey_response(client, survey_id, respondent_ids):
    postdata = {'survey_id': survey_id,
                'respondent_ids' : respondent_ids}
    return make_request(client, 'get_responses', postdata)

def get_survey_id(client, title):
    postdata = { 'title': title }
    survey_list = make_request(client, 'get_survey_list', postdata)
    surveys = survey_list['data']['surveys']
    assert len(surveys) < 2, "Multiple surveys returned!"
    if len(surveys) < 1:
        logger.debug("No surveys found.")
        return None
    return surveys[0]['survey_id']

def get_question_ids(client, survey_id):
    details = make_request(client, 'get_survey_details', {'survey_id': survey_id})
    questions = details['data']['pages'][0]['questions']
    q_ids = dict([(q['question_id'],
                   q['heading']) for q in questions if q['heading'] in QUESTIONS])
    missing = [q for q in QUESTIONS if q not in q_ids.values()]
    if len(missing):
        logger.error("Could not find questions on first page: %s",
                     missing)
        sys.exit(1)
    return q_ids

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
state_data = {}
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, 'r') as f:
            for l in f.readlines():
                (k,v) = l.strip().split('=', 1)
                state_data[k] = v
    except IOError as e:
        logger.exception("Failed to read state file")
        sys.exit(1)
else:
    logger.debug("State file does not exist, assuming past 7 days")
    state_data = {'date': time.strftime("%Y-%m-%d %H:%M:%S",
                                        time.localtime(time.time() - 604800))}
try:
    with open(STATE_FILE, 'w') as f:
        f.write("date={0}\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
except IOError as e:
    logger.exception("Failed to write state file")
    sys.exit(1)

# TODO: Cache this
survey_id = get_survey_id(client, SURVEY_TITLE)
if survey_id is None:
    logger.error("Failed to get survey id")
    sys.exit(1)
# TODO: Also cache this
q_ids = get_question_ids(client, survey_id)
respondents = {x['respondent_id']: x for x in get_respondents(client, survey_id, state_data['date'])}
output = []
if len(respondents.keys()):
    responses_json = get_survey_response(client, survey_id, respondents.keys())
    for x in responses_json['data']:
        data = {q_ids[q['question_id']].strip(':'): y['text'] for q in x['questions'] if q['question_id'] in q_ids for y in q['answers']}
        data.update(respondents[x['respondent_id']])
        output.append("* {Name} ({MIT email address}) submitted a {status} survey on {date_modified}".format(**data))
if len(output):
    header = 'Surveys updated since {0}:'.format(state_data['date'])
    output.insert(0, header)
    send_email("\n".join(output))
else:
    logger.debug("No surveys")
logger.debug("**END** at %s", time.strftime("%Y-%m-%d %H:%M"))
