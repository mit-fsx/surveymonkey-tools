#!/usr/bin/python
#
# Periodically poll SurveyMonkey for repsonses

import json
import os
import sys
import time
import logging
import subprocess

import surveymonkey

# What questions do we want from the survey?
QUESTIONS=['Name:', 'MIT email address:']

logger = logging.getLogger('poll')
sendmail_cmd = ['/usr/sbin/sendmail', '-t']

def send_email(email_to, body):
    # Remember, this is a docstring, so it must end on the line after
    # 'Subject' to provide the required blank line
    header = """To: {to}
From: CS Hiring Survey Checker <devnull@mit.edu>
Subject: New Technical Surveys
"""
    sendmail = subprocess.Popen(sendmail_cmd,
                                stdin=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    (_, err) = sendmail.communicate(header.format(to=email_to) + body)
    if sendmail.returncode != 0:
        logger.error("Failed to send mail: %s", err)
        sys.exit(1)

class SavedState():
    """Save the last date to a file"""
    LAST_N_DAYS = 30

    # SurveyMonkey dates are in UTC
    def __init__(self, config_file):
        # Default to last 7 days
        self.data = {'last_date': time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.gmtime(time.time() - (self.LAST_N_DAYS * 86400)))}
        self._config_file = config_file
        try:
            self._load()
        except (IOError, ValueError) as e:
            logger.exception("Failed to read config file")

    def __getattr__(self, attr):
         if attr in self.__dict__:
             return self.__dict__[attr]
         elif attr in self.data:
             return self.data[attr]
         raise AttributeError(
             "SavedState instance has no attribute '{0}'".format(attr))

    def _load(self):
        if os.path.exists(self._config_file):
            with open(self._config_file, 'r') as f:
                self.data.update(json.loads(f.read()))
        else:
            logger.debug("Config file doesn't exist, using defaults")

    def _save(self):
        with open(self._config_file, 'w') as f:
            f.write(json.dumps(self.data))
        
    def touch(self):
        self.data['last_date'] = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.gmtime())

    def save(self):
        try:
            self._save()
        except (IOError, ValueError) as e:
            logger.exception("Failed to write config file")

if __name__ == "__main__":
    # This ensures the logger receives all messages of debugging
    # and higher
    logger.setLevel(logging.DEBUG)
    # Set up the handlers for the debug log, and errors
    # on STDERR
    stderr_handler = logging.StreamHandler()
    # Only warning and higher will go to stderr
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)
    try:
        config = surveymonkey.Config.load()
    except surveymonkey.SurveyMonkeyError:
        logger.exception("Failed to load config")
        sys.exit(1)

    # Add the debug handler
    debug_fmt = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s',
                                  '%m/%d/%Y %H:%M:%S')
    debug_handler = logging.FileHandler(config.poll.log_file)
    debug_handler.setFormatter(debug_fmt)
    logger.addHandler(debug_handler)

    logger.debug("**BEGIN")
    monkey = surveymonkey.SurveyMonkey(config.get_token(),
                                       config.app.api_key)
    state_data = SavedState(config.poll.state_file)
    last_upd = state_data.last_date
    logger.debug("Last check was: %s", last_upd)
    # Update the datestamp now, but don't save it in case this fails.
    state_data.touch()
    output = []
    try:
        surveys = monkey.get_survey_list(title=config.poll.survey_title)
        if len(surveys) != 1:
            logger.error("ERROR: Found %d surveys for title '%s'",
                         len(surveys), config.poll.survey_title)
            sys.exit(1)
        for s in surveys:
            details = monkey.get_survey_details(s.survey_id)
            logger.debug("Retrieved details")
            respondent_list = monkey.get_survey_respondents(
                s.survey_id,
                start_modified_date = last_upd,
                fields=['date_modified', 'status'])
            logger.debug("Retrieved respondent list")
            if len(respondent_list) < 1:
                logger.info("No responses during this time")
                break
            responses = monkey.get_survey_responses(
                s.survey_id,
                *respondent_list.respondents)
            logger.debug("Retrieved responses")
            for r in responses:
                answers = [r.get_response_for_question(q) for q in
                           details.get_questions_by_heading(*QUESTIONS)]
                data = {a.heading.strip(':'): str(a) for a in answers}
                r_info = respondent_list[r.respondent_id]
                data.update(r_info.as_dict())
                data['date_modified'] = surveymonkey.DateTime(
                    r_info.date_modified).to_local(True)
                output.append("* {Name} ({MIT email address}) submitted a {status} survey on {date_modified}".format(**data))
    except surveymonkey.SurveyMonkeyError as e:
        logger.exception("Error while talking to SurveyMonkey")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected exception")
        sys.exit(1)
    if len(output) > 0:
        logger.debug("Sending e-mail...")
        header = 'Surveys updated since {0}:'.format(last_upd)
        output.insert(0, header)
        send_email('jdreed@mit.edu', "\n".join(output))
    state_data.save()
    logger.debug("**END**")
    sys.exit(0)

