#!/usr/bin/python

import sys
import os
import time
from distutils.version import StrictVersion
import requests
#from reportlab.pdfgen import canvas
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
    def __init__(self, filename):
        # Sigh.  SimpleDocTemplate is an old-style class
        SimpleDocTemplate.__init__(self, filename,
                                   pagesize=pagesizes.letter)
        self.style = getSampleStyleSheet()["Normal"]
        self.title = ''
        self.story = []
        (self.page_w, self.page_h) = pagesizes.letter

    def _table_dimensions(self, n_rows, n_cols,
                          row_size, col_size, x_offset, y_offset):
#        h_center = self.page_w/2.0
#        v_lines = [h_center + (col_size * x) for x in range(-1 * n_cols / 2,
#                                                             (n_cols / 2) + 1)]
        v_lines = [self.page_w - x_offset - (col_size * x) for x in range(0, n_cols +1)]

        h_lines = [(self.page_h - y_offset - (row_size * x)) for x in range(0, n_rows + 1)]
        return (v_lines, h_lines)
        

    def header(self, canvas, foo):
        # self.width and self.height are the dimensions of the area
        # inside the margins.
        canvas.saveState()
        canvas.drawString(self.page_w, self.page_h, 'a')
        canvas.drawString(0.0, self.page_h, 'a')
        canvas.setFont('Helvetica-Bold', 14)
        canvas.drawString(0.5 * inch, self.page_h - inch,
                          self.title)
        canvas.setLineWidth(0.1)
        col_size = 0.5 * inch
        row_size = 0.25 * inch
        offset = 0.5 * inch
        table_dimensions = self._table_dimensions(3, 8, row_size, col_size,
                                                  offset, offset)
        canvas.setFont('Helvetica', 8)
        col_headings = ['Reader #', 'Initials', 'General', 'Mac', 'Win',
                        'Net', 'Athena', 'TOTAL']
        for x,txt in zip(reversed(table_dimensions[0]), col_headings):
            canvas.drawCentredString(x + (col_size * 0.5),
                                     table_dimensions[1][1] + 7.0, txt)
        for i,y in enumerate(table_dimensions[1][2:], start=1):
            canvas.drawCentredString(table_dimensions[0][-1] + (0.5 * col_size),
                                     y + 7.0, 
                                     str(i))
        canvas.grid(*table_dimensions)
        canvas.restoreState()

    def add_heading(self, text):
        self.add_paragraph(text)

    def add_paragraph(self, text):
        # Paragraph secretly converts to XML without escaping.
        # Because why not
        text = xmlescape(text)
        p = Paragraph(text, self.style)
        self.story.append(p)
#        self.story.append(Spacer(1, 0.2*inch))

    def add_page_break(self):
        self.story.append(PageBreak())

    def go(self):
        self.build(self.story, onFirstPage=self.header)


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
    pdf.add_heading(page['heading'])
    # Should already be sorted, but...
    # 'presentation' questions have no response
    for q in sorted([x for x in page['questions'] if x['type']['family'] != 'presentation'], key=lambda x: x['position']):
        pdf.add_paragraph(u"{0}".format(q['heading']))
        result = "(no response)"
        if q['question_id'] in responses:
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
        pdf.add_paragraph(result)

pdf.go()
