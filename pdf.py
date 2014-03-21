#!/usr/bin/python

import cgi
import cgitb
import os
import sys
import re
import urlparse
if '--debug' not in sys.argv:
    cgitb.enable()

import surveymonkey
import techdiagnostic

config = surveymonkey.Config.load()
monkey = surveymonkey.SurveyMonkey(config.get_token(),
                      config.app.api_key)


formdata = cgi.FieldStorage()
try:
    survey_id=formdata['survey_id'].value
    respondent_id=formdata['respondent_id'].value
    date=formdata['date'].value
    status=formdata['status'].value
except KeyError as e:
    if '--debug' not in sys.argv:
        print """Content-type: text/html

<html><head><title>Survey Monkey Thingy</title></head>
<body>
<p>Required parameters missing in URL: {0}</p>
</body>
</html>
""".format(e)
        sys.exit(0)

if '--debug' in sys.argv:
    dct = dict(urlparse.parse_qsl(sys.stdin.readline().strip()))
    survey_id=dct['survey_id']
    respondent_id=dct['respondent_id']
    date=dct['date']
    status=dct['status']


#respondent_id='2799054163'

details = monkey.get_survey_details(survey_id)
responses = monkey.get_survey_responses(survey_id, respondent_id,
                                        by_id=True)
if len(responses) != 1:
    print """Content-type: text/html

<html><head><title>Survey Monkey Thingy</title></head>
<body>
No responses found.
</body>
</html>
"""
    sys.exit(0)
response = responses[0]
pdf = techdiagnostic.PDF(sys.stderr)
(name, email) = [str(response.get_response_for_question(q)) for q
                 in details.get_questions_by_heading('Name:',
                                                     'MIT email address:')]
pdf.header_lines.append(name)
pdf.header_lines.append(email)
pdf.header_lines.append("{0} {1}".format(status, date))
pdf.title = 'Technical Diagnostic for {0} ({1})'.format(name, email)
filename='tech_diagnostic_{0}.pdf'.format(re.sub('[^\w@\.\-]+', '', email))
for page in details.pages:
    if len(page) == 0:
        continue
    pdf.add_page_title(page.heading)
    # TODO: enumerate?
    for question in page:
        question_response = response.get_response_for_question(question)
        pdf.add_question_response(question_response)
    pdf.add_page_break()
print "Content-disposition: inline;filename={0}\nContent-type: application/pdf\n".format(filename)
pdf.save()
