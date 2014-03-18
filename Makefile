all:
	@echo "Valid targets: install"

install:
	install -m 755 poll.py /mit/helpdesk/cron_scripts
	install -m 755 poll-setup.py /mit/helpdesk/web_scripts/surveymonkey

.PHONY: all