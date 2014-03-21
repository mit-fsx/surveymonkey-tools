#!/usr/bin/python
#
# Obtain the OAuth token

import cgi
import cgitb
import os
import sys
cgitb.enable()

import surveymonkey

config = surveymonkey.Config.load()
oauth = surveymonkey.OAuth(**config.app.as_dict())

formdata = cgi.FieldStorage()
if 'go' in formdata:
    # Redirect to login page
    print "Location: {0}\n".format(oauth.auth_uri)
    sys.exit(0)

print """Content-type: text/html

<html><head><title>Survey Monkey Thingy - OAuth Token</title></head>
<body>"""

if 'code' in formdata:
    # We were given the code from the authorization URI
    # Convert into a token
    code = formdata['code'].value
    try:
        oauth.get_and_save_token(code, config.token_file)
        print "<p><strong>Success: </strong>Obtained new oaut token.</p>"
    except SurveyMonkeyError as e:
        print "<p><strong>ERROR: </strong>Error while obtaining token.</p>"
        print "<pre>{0}</pre>".format(e)
elif 'error' in formdata:
    print "<p><strong>ERROR: </strong>Error while obtaining token.</p>"
    print "<pre>{0}: {1}</pre>".format(formdata['error'].value,
                                       formdata['error_description'].value)

print '<form name="login" method="post" action="{0}">'.format(
    os.getenv('SCRIPT_NAME'))
print '<input type="submit" name="go" value="Obtain OAuth Token"/>'
if os.path.exists(config.token_file):
    print ' (<strong>WARNING: </strong>Token file already exists.  It will ' \
        'be overwritten.  Make sure this is what you want.)'
print '</form></body></html>'
sys.exit(0)



