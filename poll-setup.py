#!/usr/bin/python

import cgi
import cgitb
import os
import sys
import requests
import urllib
import json

CONFIG_FILE="/afs/athena.mit.edu/astaff/project/helpdesk" \
    "/web_scripts/surveymonkey/private/config.json"

cgitb.enable()
if not os.getenv('REMOTE_ADDR','').startswith('18.'):
    print "Content-type: text/plain\n"
    print "This application must be accessed on-campus or with the VPN."
    sys.exit(0)

# Load the config file
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.loads(f.read())
except (ValueError, IOError) as e:
    print "Content-type: text/plain\n"
    print "Error reading config file: ", e
    sys.exit(0)

formdata = cgi.FieldStorage()
if 'go' in formdata:
    url = "{0}{1}?{2}".format(config['api']['base'],
                              config['api']['auth_endpoint'],
                              urllib.urlencode(
            {'redirect_uri': config['app']['redirect_uri'],
             'client_id': config['app']['client_id'],
             'api_key': config['app']['api_key'],
             'response_type': 'code'}))
    # Redirect to login page
    print "Location: {0}\n".format(url)
    sys.exit(0)

if 'code' in formdata:
    # We were given the code from the authorization URI
    # Convert into a token
    code = formdata['code'].value
    request_data = {'code': code,
                    'client_secret': config['app']['client_secret'],
                    'redirect_uri': config['app']['redirect_uri'],
                    'client_id': config['app']['client_id'],
                    'grant_type': 'authorization_code'}
    # Note the URI we POST to has the api_key as part of the
    # query string.  It cannot be encoded in POST data.
    token_uri = "{0}{1}?api_key={2}".format(config['api']['base'],
                                            config['api']['token_endpoint'],
                                            config['app']['api_key'])
    token_response = requests.post(token_uri, data=request_data)
    print "Content-type: text/plain\n"
    try:
        token_json = token_response.json()
    except ValueError:
        print "Did not receive JSON response from token endpoint."
        print "Response:"
        print token_response
        sys.exit(0)
    if 'access_token' not in token_json:
        print "Failed to acquire token: "
        print token_json['error_description']
        sys.exit(0)
    try:
        with open(config['token_file'], 'w') as f:
            f.write(token_json['access_token'])
            print "Successfully wrote token to file."
    except (IOError, KeyError) as e:
        print "Failed to write token to file: ", e
    sys.exit(0)
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
if os.path.exists(config['token_file']):
    print '<p><strong>WARNING: </strong>Token file already exists.  It will ' \
        'be overwritten.  Make sure this is what you want.</p>'
print '<form name="login" method="post" action="{0}">'.format(
    os.getenv('SCRIPT_NAME'))
print '<input type="submit" name="go" value="Continue"/>' \
    '</form>'
print "</body></html>"
sys.exit(0)



