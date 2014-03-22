#!/usr/bin/python

import cgi
import cgitb
import os
import sys
import re
import urlparse

# Hack for easy debugging
debug_mode = 'GATEWAY_INTERFACE' not in os.environ

if not debug_mode:
    cgitb.enable()

sys.path.append(os.path.join(os.getcwd(), 'lib'))
import surveymonkey
import techdiagnostic

config = surveymonkey.Config.load()
monkey = surveymonkey.SurveyMonkey(config.get_token(),
                                   config.app.api_key)

formdata = cgi.FieldStorage()
if debug_mode:
    # Populdate FieldStorage from urlencoded data on stdin
    print "CGI debugging mode; enter one line of url-encoded data."
    for k,v in urlparse.parse_qsl(sys.stdin.readline().strip()):
        print "{0}={1}".format(k,v)
        formdata.list.append(cgi.MiniFieldStorage(k,v))
try:
    survey_id=formdata['survey_id'].value
    respondent_id=formdata['respondent_id'].value
    date=formdata['date'].value
    status=formdata['status'].value
except KeyError as e:
    if debug_mode:
        sys.exit("Parameter missing: " + str(e))
    print """Content-type: text/html

<html><head><title>Survey Monkey Thingy</title></head>
<body>
<p>Required parameters missing in URL: {0}</p>
</body>
</html>
""".format(e)
    sys.exit(0)

details = monkey.get_survey_details(survey_id)
responses = monkey.get_survey_responses(survey_id, respondent_id,
                                        by_id=True)
if len(responses) != 1:
    err = "Multiple" if len(responses) else "No"
    if debug_mode:
        sys.exit('{0} responses found for respondent_id {1}.'.format(
                err, respondent_id))
    print """Content-type: text/html

<html><head><title>Survey Monkey Thingy</title></head>
<body>
Error: {0}
</body>
</html>
""".format(err)
    sys.exit(0)

response = responses.pop()
pdf = techdiagnostic.PDF("output.pdf" if debug_mode else sys.stdout)
# Pull out name and email for headers
(name, email) = [str(response.get_response_for_question(q)) for q
                 in details.get_questions_by_heading('Name:',
                                                     'MIT email address:')]
pdf.header_lines.append(name)
pdf.header_lines.append(email)
pdf.header_lines.append("{0} {1}".format(status, date))
# The title of the PDF itself
pdf.title = 'Technical Diagnostic for {0} ({1})'.format(name, email)
# The filename, for Content-disposition purposes only.
filename='tech_diagnostic_{0}.pdf'.format(re.sub('[^\w@\.\-]+', '', email))
for page in details.pages:
    if len(page) == 0:
        continue
    section = techdiagnostic.Section(page.heading)
    if page.heading == 'Basic Information':
        section.skip_footer = True
        section.skip_question_numbers = True
        section.inline_single_answers = [
            'Name:', 'MIT email address:',
            'Phone Number (cell phone preferred):']
    pdf.add_section(section)
    pdf.add_page_title(page.heading)
    for question in page:
        question_response = response.get_response_for_question(question)
        pdf.add_question_response(question_response)
    pdf.add_page_break()
if debug_mode:
    print "Successfully generated", pdf.filename
    print "Would have sent filename of", filename
else:
    print "Content-disposition: inline;filename={0}".format(filename)
    print "Content-type: application/pdf\n".format(filename)
pdf.save()
sys.exit(0)
