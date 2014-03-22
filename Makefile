#TODO: Replace this with distutils

MODULES=surveymonkey.py techdiagnostic.py
WEBSCRIPTS=get_token.py pdf.py monkey.py
CRONSCRIPTS=poll.py

LOCKER=/mit/helpdesk
CRONDIR=$(LOCKER)/cron_scripts
WEBDIR=$(LOCKER)/web_scripts/surveymonkey
MODULEDIR=$(WEBDIR)/lib

all:
	@echo "Valid targets: install"

install:
	install -m 755 $(CRONSCRIPTS) $(CRONDIR)
	install -m 644 $(MODULES) $(MODULEDIR)
	install -m 755 $(WEBSCRIPTS) $(WEBDIR)

.PHONY: all