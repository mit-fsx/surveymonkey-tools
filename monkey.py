#!/usr/bin/python -u
# We want -u to trick browser into thinking that the page is loading

import cgi
import cgitb
import os
import sys
import time
import urllib
cgitb.enable()

import surveymonkey
import techdiagnostic

config = surveymonkey.Config.load()
oauth = surveymonkey.OAuth(**config.app.as_dict())

numdays = 30
formdata = cgi.FieldStorage()
print """Content-type: text/html

<html><head><title>Survey Monkey Thingy</title></head>
<body>"""
try:
    numdays=int(formdata['numdays'].value)
except KeyError:
    pass
except ValueError:
    print "<p>Bad value for 'numdays'</p>"
    print "</body></html>"
    sys.exit(0)

monkey = surveymonkey.SurveyMonkey(config.get_token(),
                                   config.app.api_key)

print "<h1>Survey responses in last {0} days</h1>".format(numdays)
try:
    surveys = monkey.get_survey_list(title='Student Application and Technical Survey')
    if len(surveys) < 1:
        print "<p><strong>ERROR:</strong> No surveys found with title '{0}'".format(config.survey_title)
    for s in surveys:
        details = monkey.get_survey_details(s.survey_id)
        print "<h2>{0}</h2>".format(s.title)
        date_interval = time.strftime("%Y-%m-%d %H:%M:%S",
                                      time.gmtime(time.time() - 86400 * numdays))
        respondent_list = monkey.get_survey_respondents(s.survey_id,
                                                    start_date=date_interval,
                                                    fields=['date_modified',
                                                            'status'])
        if len(respondent_list) < 1:
            print "<p>(no responses during this time)</p>"
            break
        responses = monkey.get_survey_responses(s.survey_id,
                                                *respondent_list.respondents)
        print "<table border=\"1\"><tr><th>Name</th><th>Email</th><th>date</th><th>status</th><th>PDF</th></tr>"
        for r in responses:
            print "<tr>"
            for q in details.get_questions_by_heading('Name:',
                                                      'MIT email address:'):
                answer = r.get_response_for_question(q)
                print "<td>{0}</td>".format(answer.answer[0] if answer else '<n/a>')
            r_info = respondent_list[r.respondent_id]
            date_modified = surveymonkey.DateTime(r_info.date_modified).to_local(True)
            print "<td>{0}</td><td>{1}</td>".format(date_modified,
                                                    r_info.status)
            urldata = urllib.urlencode({'survey_id': s.survey_id,
                                        'respondent_id': r.respondent_id,
                                        'date': date_modified,
                                        'status': r_info.status})
            print """<td>
                     <a href=\"{0}\" target=\"_blank\">Go</a>
                     </td></tr>""".format(
                "pdf.py?{0}".format(urldata))
        print "</table>"
except surveymonkey.SurveyMonkeyError as e:
    print "ERROR:", e
print '<form name="days" method="post" action="{0}">'.format(
    os.getenv('SCRIPT_NAME'))
print 'View the last <select name="numdays">'
for n in range(30, 365, 30):
    print '<option value="{0}">{1}</option>'.format(n, n)
print '</select> days'
print '<input type="submit" name="go" value="Update"/>'
print '</form>'
print "</body></html>"
sys.exit(0)



