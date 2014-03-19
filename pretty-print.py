#!/usr/bin/python

import json
import logging
import os
import subprocess
import sys
import time
import re

from distutils.version import StrictVersion
from xml.sax import saxutils

from reportlab.lib import pagesizes, styles, units, enums
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.pdfbase.pdfmetrics import stringWidth
import requests

# Sanity checking
if StrictVersion(requests.__version__) < StrictVersion('1.1.0'):
    print >>sys.stderr, "Version 1.1.0 of the 'requests' library is required."
    print >>sys.stderr, "For convenience, there is a copy in /mit/helpdesk/src"
    sys.exit(1)

# Preferences for how things are rendered.
# Page headings (in the survey) for which we skip question numbers,
# and which allow toplevel "inline" formatted questions.
page_render_prefs = { 'skip_question_numbers': ('Basic Information',),
                      'allow_toplevel_inline': ('Basic Information',) }

class Question:
    """
    Representing a question on a survey, possibly with sub-questions.
    """
    _formats = ('paragraph', 'inline', 'bullet', 'unformatted')

    def __init__(self, heading, num=None):
        self.num = num
        self.heading = heading.strip()
        self.format = 'paragraph'
        self.subquestions = []
        self.answers = []

    def add_to_pdf(self, pdf, q_style='Question'):
        assert self.format in self._formats, self.format
        if self.format == 'unformatted':
            pdf.add_paragraph(self._get_heading(), style=q_style)
            pdf.add_paragraph(repr(self.answers), style='Error')
        if self.format == 'inline':
            answers = self._get_answers()
            assert len(answers) == 1, "inline question has > 1 answers"
            if pdf._will_fit_inline(self._get_heading(), 'Inline'+q_style):
                pdf.add_paragraph(answers[0], style='Inline'+q_style,
                                  bulletText=self._get_heading())
            else:
                self.format = 'paragraph'
        if self.format == 'bullet':
            pdf.add_paragraph(self._get_heading(), style=q_style)
            for a in self._get_answers():
                pdf.add_paragraph(a, style='Answer', bulletText=u"\u2022")
        if self.format == 'paragraph':
            pdf.add_paragraph(self._get_heading(), style=q_style)
            if len(self.subquestions) > 0:
                for q in self.subquestions:
                    q.add_to_pdf(pdf, 'Subquestion')
            else:
                for a in self._get_answers():
                    pdf.add_paragraph(a, style='Answer')

    def _get_heading(self):
        rv = u''
        if self.num is not None:
            rv += u'{0}. '.format(self.num)
        return rv + self.heading

    def _get_answers(self):
        assert len(self.subquestions) == 0, "Answer has subquestions"
        return [u'(no response)'] if len(self.answers) == 0 else self.answers

    def add_subquestion(self, subquestion):
        assert len(self.answers) == 0
        if re.match(r'[a-z]\)\s*$', subquestion.heading):
            subquestion.format = 'inline'
        self.subquestions.append(subquestion)

    def add_answer(self, answer):
        assert len(self.subquestions) == 0
        self.answers.append(answer)

    def add_unformatted(self, q_type, answers):
        assert len(self.subquestions) == 0
        self.format = 'unformatted'
        self.add_answer(
            u"ERROR: CANNOT FORMAT {0}/{1} QUESTION".format(q_type['family'],
                                                            q_type['subtype']))

    def __repr__(self):
        rv = u"Question({0})\n\tformat={1}\n".format(self.heading, self.format)
        rv += u"\tAnswer: {0}\n".format(self.answers)
        rv += u"\tSubquestions: {0}".format(repr(self.subquestions))
        return rv.encode("utf-8")

class StyleSheet(dict):
    def __init__(self):
        super(StyleSheet, self).__init__()
        self['Normal'] = styles.ParagraphStyle('Normal', parent=None,
                                               fontName='Helvetica',
                                               fontSize=10, leading=12)
        self['Title'] = styles.ParagraphStyle('Title', parent=self['Normal'],
                                              alignment=enums.TA_CENTER,
                                              fontName='Helvetica-Bold',
                                              fontSize=18, leading=22,
                                              spaceAfter=6)
        self['Question'] = styles.ParagraphStyle('Question',
                                                 parent=self['Normal'],
                                                 fontName='Helvetica-Bold',
                                                 fontSize=12, leading=12,
                                                 spaceBefore=6, spaceAfter=4)
        self['Subquestion'] = styles.ParagraphStyle('Subquestion',
                                                    parent=self['Question'],
                                                    fontName='Helvetica-Bold',
                                                    fontSize=10,
                                                    leftIndent=6,
                                                    spaceBefore=4, spaceAfter=2)
        self['Answer'] = styles.ParagraphStyle('Answer',
                                               parent=self['Normal'],
                                               fontName='Courier',
                                               leftIndent=12,
                                               bulletIndent=6)
        self['Error'] = styles.ParagraphStyle('Error',
                                              parent=self['Answer'],
                                              backColor='yellow')
        for sheet in ('Question', 'Subquestion'):
            name = 'Inline' + sheet
            self[name] = styles.ParagraphStyle(
                name, parent=self[sheet],
                bulletIndent=self[sheet].leftIndent,
                bulletFontName=self[sheet].fontName,
                bulletFontSize=self[sheet].fontSize,
                leftIndent=(self[sheet].leftIndent *
                            1.5) + self['Answer'].leftIndent,
                fontName=self['Answer'].fontName)
        for sheet in self.keys():
            self[sheet+'Start'] = styles.ParagraphStyle(sheet+'Start',
                                                        parent=self[sheet],
                                                        spaceAfter=0)
            self[sheet+'Mid'] = styles.ParagraphStyle(sheet+'Mid',
                                                      parent=self[sheet],
                                                      spaceBefore=0,
                                                      spaceAfter=0)
            self[sheet+'End'] = styles.ParagraphStyle(sheet+'End',
                                                      parent=self[sheet],
                                                      spaceBefore=0)


class TechDiagnosticPDF(SimpleDocTemplate):
    meta_headings = { 'Name:': '_hdr_name',
                      'MIT email address:': '_hdr_email'
                      }

    def __init__(self, filename):
        # Sigh.  SimpleDocTemplate is an old-style class
        SimpleDocTemplate.__init__(self, filename,
                                   pagesize=pagesizes.letter)
        self.stylesheet = StyleSheet()
        self._hdr_name = '<name>'
        self._hdr_email = '<email>'
        self._hdr_date = 'Printed: ' + time.strftime('%Y-%m-%d %H:%M')
        self._cur_page_title = 'Untitled'
        # This way we can use list indicies, since there's no Page 0
        self._pages = [None]
        # Start with a Sapcer for the header on the first page
        self.story = [Spacer(1, 1.5 * units.inch)]
        self.leftMargin = 0.5 * units.inch
        self.rightMargin = self.leftMargin
        self.topMargin = 0.5 * units.inch
        self.bottomMargin = 0.75 * units.inch
        (self.page_w, self.page_h) = pagesizes.letter

    def _scoring_table(self, canvas, data, **kwargs):
        row_height = kwargs.get('row_height', None)
        col_width = kwargs.get('col_width', None)
        assert row_height is not None
        assert col_width is not None
        x_offset = kwargs.get('x_offset', 0.5 * units.inch)
        y_offset = kwargs.get('y_offset', 0.5 * units.inch)
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

    def _will_fit_inline(self, txt, style):
        sheet = self.stylesheet[style]
        return stringWidth(
            txt, sheet.bulletFontName,
            sheet.bulletFontSize) <= (self.leftMargin + (self.page_w * 0.5))

    def _header(self, canvas, _):
        # self.width and self.height are the dimensions of the area
        # inside the margins.
        canvas.saveState()
        canvas.setFont('Helvetica-Bold', 14)
        for row,txt in enumerate([self._hdr_name, self._hdr_email,
                                  self._hdr_date], start=1):
            canvas.drawRightString(self.page_w - (0.5 * units.inch),
                                   self.page_h - (0.45 * units.inch) - (row *
                                                                  0.25 *
                                                                  units.inch),
                                   txt)
        table_data = [['Reader #', 'Initials', 'General', 'Mac', 'Win',
                       'Net', 'Athena', 'TOTAL'],
                      ['1'],
                      ['2']]
        canvas.setLineWidth(0.1)
        self._scoring_table(canvas, table_data,
                            row_height = 0.25 * units.inch,
                            col_width = 0.5 * units.inch)
        canvas.restoreState()

    def _footer(self, canvas, _):
        canvas.saveState()
        canvas.setFont('Helvetica', 10)
        canvas.drawRightString(self.page_w - (0.75 * units.inch),
                               0.5 * units.inch,
                               u'"{0}" score: '.format(self._pages[self.page]))
        canvas.line(self.page_w - (0.75 * units.inch),
                    0.5 * units.inch,
                    self.page_w - (0.5 * units.inch),
                    0.5 * units.inch)

        canvas.drawString(0.5 * units.inch,
                          0.5 * units.inch,
                          'Page {0}'.format(self.page))
        canvas.restoreState()

    def add_page_title(self, text):
        self._cur_page_title = text
        self.add_paragraph(text, style='Title')

    def add_question(self, question):
        if question.heading in self.meta_headings:
            setattr(self, self.meta_headings[question.heading],
                    question.answers[0])
        question.add_to_pdf(self)

    def add_paragraph(self, text, **kwargs):
        # Paragraph class takes XML for formatting, so
        # we must escape our unformatted text
        if not kwargs.pop('xml', False):
            text = saxutils.escape(text)
        style = kwargs.pop('style', 'Normal')
        # Deal with questions which have newlines in them.
        # SurveyMonkey renders these with linebreaks, so
        # we expect to see them.
        paragraphs = text.split('\r\n')
        for txt,style in zip(paragraphs,
                             [style + x for x in
                              ['Start' if len(paragraphs) > 1 else ''] +
                              ['Mid'] * (len(paragraphs) - 2) + ['End']
                              ]):
            self.story.append(Paragraph(txt, self.stylesheet[style], **kwargs))

    def add_page_break(self):
        self._pages.append(self._cur_page_title)
        self.story.append(PageBreak())

    def save(self):
        self.build(self.story,
                   onFirstPage=self._header,
                   onLaterPages=self._footer)


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

for page in pages:
    # Skip pages with no questions (e.g. informational)
    if len(page['questions']) == 0:
        continue
    pdf.add_page_title(page['heading'])
    # 'presentation' questions have no response, remove them
    questions = [x for x in page['questions']
                 if x['type']['family'] != 'presentation']
    # Should already be sorted, but...
    for n, q in enumerate(sorted(questions,
                                 key=lambda x: x['position']),
                          start=1):
        if page['heading'] in page_render_prefs['skip_question_numbers']:
            n=None
        question = Question(q['heading'], n)
        if q['question_id'] in responses:
            answers = responses[q['question_id']]
            if q['type']['family'] == 'open_ended':
                if q['type']['subtype'] == 'multi':
                    for answer_heading in sorted([x for x in q['answers']],
                                                 key=lambda x: x['position']):
                        subquestion = Question(answer_heading['text'])
                        subquestion.format = 'inline'
                        answer = [a for a in answers
                                  if a['row'] == answer_heading['answer_id']]
                        assert len(answer) < 2
                        if len(answer) == 1:
                            subquestion.add_answer(answer[0]['text'])
                        question.add_subquestion(subquestion)
                elif q['type']['subtype'] in ('essay', 'single'):
                    assert len(answers) == 1
                    assert answers[0]['row'] == '0'
                    question.add_answer(answers[0]['text'])
                    if (page['heading'] in
                        page_render_prefs['allow_toplevel_inline']) \
                        and (q['type']['subtype'] == 'single'):
                        question.format = 'inline'
                else:
                    question.add_unformatted(q['type'], answers)
            else:
                for ans in answers:
                    rows = [a for a in q['answers']
                            if a['answer_id'] == ans['row']]
                    assert len(rows) == 1
                    if q['type']['family'] == 'multiple_choice':
                        question.format = 'bullet'
                    if rows[0]['type'] == 'other':
                        question.add_answer(u'{0}: {1}'.format(rows[0]['text'],
                                                               ans['text']))
                    elif rows[0]['type'] == 'row':
                        question.add_answer(rows[0]['text'])
                    else:
                        question.add_unformatted(q['type'], answer)
        pdf.add_question(question)
    pdf.add_page_break()

pdf.save()
