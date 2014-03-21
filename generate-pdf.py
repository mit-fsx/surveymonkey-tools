#!/usr/bin/python

import surveymonkey
import techdiagnostic

config = surveymonkey.Config.load()
monkey = surveymonkey.SurveyMonkey(config.get_token(),
                      config.app.api_key)

survey_id='20816427'
respondent_id='3122352155'
respondent_id='2803655571'
respondent_id='2799054163'

details = monkey.get_survey_details(survey_id)
responses = monkey.get_survey_responses(survey_id, respondent_id)
if len(responses) != 1:
    sys.exit("error")
response = responses[respondent_id]

pdf = techdiagnostic.PDF("output.pdf")
for q in details.get_questions_by_heading('Name:', 'MIT email address:'):
    answer = response.get_response_for_question(q)
    pdf.header_lines.append(answer.answer[0] if answer else '<n/a>')
pdf.header_lines.append('date here')

for page in details.pages:
    if len(page) == 0:
        continue
    pdf.add_page_title(page.heading)
    # TODO: enumerate?
    for question in page:
        question_response = response.get_response_for_question(question)
        pdf.add_question_response(question_response)
    pdf.add_page_break()

pdf.save()
