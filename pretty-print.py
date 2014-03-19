#!/usr/bin/python

import sys
import os
import copy
import time
from distutils.version import StrictVersion
import requests
from reportlab.lib import pagesizes
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from xml.sax.saxutils import escape as xmlescape

if StrictVersion(requests.__version__) < StrictVersion('1.1.0'):
    print >>sys.stderr, "Version 1.1.0 of the 'requests' library is required."
    print >>sys.stderr, "For convenience, there is a copy in /mit/helpdesk/src"
    sys.exit(1)
import json
import logging
import subprocess

class TechDiagnosticPDF(SimpleDocTemplate):
    meta_headings = { 'Name:': '_hdr_name',
                      'MIT email address:': '_hdr_email'
                      }
    
    def __init__(self, filename):
        # Sigh.  SimpleDocTemplate is an old-style class
        SimpleDocTemplate.__init__(self, filename,
                                   pagesize=pagesizes.letter)
        sample = getSampleStyleSheet()
        self.stylesheet = dict()
        self.stylesheet['Title'] = sample['Title']
        self.stylesheet['Normal'] = sample['Normal']
        for s in ('Question', 'SubQuestion', 'Answer'):
            self.stylesheet[s] = copy.deepcopy(sample['Normal'])
        self.stylesheet['Question'].fontName = 'Helvetica-Bold'
        self.stylesheet['Question'].fontSize = 12
        self.stylesheet['SubQuestion'].fontName = 'Helvetica-Bold'
        self.stylesheet['SubQuestion'].fontSize = 10
        self.stylesheet['Answer'].fontName = 'Courier'
        self._hdr_name = '<name>'
        self._hdr_email = '<email>'
        self._hdr_date = 'Printed: ' + time.strftime('%Y-%m-%d %H:%M')
        self.current_page = None
        # Start with a Sapcer for the header on the first page
        self.story = [Spacer(1, 0.75 * inch)]
        (self.page_w, self.page_h) = pagesizes.letter

    def _scoring_table(self, canvas, data, **kwargs):
        row_height = kwargs.get('row_height', None)
        col_width = kwargs.get('col_width', None)
        assert row_height is not None
        assert col_width is not None
        x_offset = kwargs.get('x_offset', 0.5 * inch)
        y_offset = kwargs.get('y_offset', 0.5 * inch)
        align = kwargs.get('align', 'left')
        n_rows = len(data)
        n_cols = max([len(x) for x in data])
        rng = range(0, n_cols +1)
        if align == 'right':
            rng = range(-1 * n_cols, 1)
            x_offset = self.page_w - x_offset
        v_lines = [x_offset + (col_width * x) for x in rng]
        h_lines = [(self.page_h - y_offset -
                    (row_height * x)) for x in range(0, n_rows + 1)]
        canvas.grid(v_lines, h_lines)
        canvas.setFont('Helvetica', 8)
        for y, row in enumerate(data, start=1):
            for x,txt in zip(v_lines, row):
                canvas.drawCentredString(x + (col_width * 0.5),
                                         h_lines[y] + 7.0, txt)
        

    def _header(self, canvas, foo):
        # self.width and self.height are the dimensions of the area
        # inside the margins.
        canvas.saveState()
        canvas.setFont('Helvetica-Bold', 14)
        for row,txt in enumerate([self._hdr_name, self._hdr_email,
                                  self._hdr_date], start=1):
            canvas.drawRightString(self.page_w - (0.5 * inch),
                                   self.page_h - (0.45 * inch) - (row *
                                                                  0.25 *
                                                                  inch),
                                   txt)
        table_data = [['Reader #', 'Initials', 'General', 'Mac', 'Win',
                       'Net', 'Athena', 'TOTAL'],
                      ['1'],
                      ['2']]
        canvas.setLineWidth(0.1)
        self._scoring_table(canvas, table_data,
                            row_height = 0.25 * inch,
                            col_width = 0.5 * inch)
        canvas.restoreState()

    def add_page_title(self, text):
        self.current_section = text
        self.add_paragraph(text, 'Title')

    def add_question(self, text):
        self.add_paragraph(text, 'Question')

    def add_subquestion(self, text):
        self.add_paragraph(text, 'SubQuestion')

    def add_answer(self, text):
        self.add_paragraph(text, 'Answer')

    def add_paragraph(self, text, style='Normal'):
        # Paragraph secretly converts to XML without escaping.
        # Because why not
        text = xmlescape(text)
        p = Paragraph(text, self.stylesheet[style])
        self.story.append(p)

    def add_page_break(self):
        self.story.append(PageBreak())

    def check_and_set_metadata(self, heading, value):
        if heading in self.meta_headings:
            setattr(self, self.meta_headings[heading], value)

    def go(self):
        self.build(self.story, onFirstPage=self._header)


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

pdf = TechDiagnosticPDF("output.pdf")
pdf.title = title

# print
#print title
for page in pages:
    # Skip pages with no questions (e.g. informational)
    if len(page['questions']) == 0:
        continue
    # Whee, Unicode
    pdf.add_page_title(page['heading'])
    # Should already be sorted, but...
    # 'presentation' questions have no response
    for q in sorted([x for x in page['questions'] if x['type']['family'] != 'presentation'], key=lambda x: x['position']):
        heading = q['heading']
        pdf.add_question(u"{0}: {1}".format(q['position'], heading))
        result = "(no response)"
        if q['question_id'] in responses:
            answers = responses[q['question_id']]
            if q['type']['family'] == 'open_ended':
                if q['type']['subtype'] == 'multi':
                    for answer_heading in sorted([x for x in q['answers']],
                                                 key=lambda x: x['position']):
                        pdf.add_subquestion(answer_heading['text'])
                        answer = [a for a in answers
                                  if a['row'] == answer_heading['answer_id']]
                        assert len(answer) < 2
                        if len(answer) == 0:
                            pdf.add_answer('(no response)')
                        else:
                            pdf.add_answer(answer[0]['text'])
                elif q['type']['subtype'] in ('essay', 'single'):
                    assert len(answers) == 1
                    assert answers[0]['row'] == '0'
                    result = answers[0]['text']
                    pdf.add_answer(answers[0]['text'])
                else:
                    pdf.add_answer('<UNABLE TO RENDER ANSWER>')
            else:
                for ans in answers:
                    rows = [a for a in q['answers'] if a['answer_id'] == ans['row']]
                    assert len(rows) == 1
                    if rows[0]['type'] == 'other':
                        pdf.add_answer(u'{0}: {1}'.format(rows[0]['text'],
                                                          ans['text']))
                    elif rows[0]['type'] == 'row':
                        pdf.add_answer(rows[0]['text'])
                    else:
                        pdf.add_answer('<UNABLE TO RENDER ANSWER>')
        pdf.check_and_set_metadata(heading, result)
    pdf.add_page_break()

pdf.go()
