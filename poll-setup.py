#!/usr/bin/python

import cgi
import cgitb
import os
import sys
cgitb.enable()

import surveymonkey
import techdiagnostic

if not os.getenv('REMOTE_ADDR','').startswith('18.'):
    print "Content-type: text/plain\n"
    print "This application must be accessed on-campus or with the VPN."
    sys.exit(0)

config = surveymonkey.Config.load()
oauth = surveymonkey.OAuth(**config.app.as_dict())

formdata = cgi.FieldStorage()
if 'go' in formdata:
    # Redirect to login page
    print "Location: {0}\n".format(oauth.auth_uri)
    sys.exit(0)

if 'code' in formdata:
    # We were given the code from the authorization URI
    # Convert into a token
    code = formdata['code'].value
    print "Content-type: text/plain\n"
    oauth.get_and_save_token(code, config.token_file)
elif 'error' in formdata:
    print "Content-type: text/plain\n"
    print "{0}: {1}".format(formdata['error'].value,
                            formdata['error_description'].value)
    sys.exit(0)
    
# Print an HTML header
print 'Content-type: text/html\n\n' \
    '<html><head><title>Survey Monkey Response Thingy</title></head>' \
    '<body>'
print "<p>This will let you log in to SurveyMonkey " \
    "and initialize this application.</p>"
if os.path.exists(config.token_file):
    print '<p><strong>WARNING: </strong>Token file already exists.  It will ' \
        'be overwritten.  Make sure this is what you want.</p>'
print '<form name="login" method="post" action="{0}">'.format(
    os.getenv('SCRIPT_NAME'))
print '<input type="submit" name="go" value="Continue"/>' \
    '</form>'
print "</body></html>"
sys.exit(0)



