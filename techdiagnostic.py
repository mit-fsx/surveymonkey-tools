"""Generate PDF for the Technical Diagnostic"""

import logging
import sys

from xml.sax import saxutils

from reportlab.lib import pagesizes, styles, units, enums
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.platypus.flowables import NullDraw
from reportlab.pdfbase.pdfmetrics import stringWidth

class StyleSheet(dict):
    def __init__(self):
        super(StyleSheet, self).__init__()
        # Base style
        self['Normal'] = styles.ParagraphStyle('Normal', parent=None,
                                               fontName='Helvetica',
                                               fontSize=10, leading=12)
        # The title of a page or section
        self['Title'] = styles.ParagraphStyle('Title', parent=self['Normal'],
                                              alignment=enums.TA_CENTER,
                                              fontName='Helvetica-Bold',
                                              fontSize=18, leading=22,
                                              spaceAfter=8)
        self['Question'] = styles.ParagraphStyle('Question',
                                                 parent=self['Normal'],
                                                 fontName='Helvetica-Bold',
                                                 fontSize=12, leading=12,
                                                 spaceBefore=8, spaceAfter=4)
        self['Subquestion'] = styles.ParagraphStyle('Subquestion',
                                                    parent=self['Question'],
                                                    fontName='Helvetica-Bold',
                                                    fontSize=10,
                                                    leftIndent=6,
                                                    spaceBefore=4, spaceAfter=2)
        # Courier needs less leading than other fonts
        self['Answer'] = styles.ParagraphStyle('Answer',
                                               parent=self['Normal'],
                                               fontName='Courier',
                                               leading=10.5,
                                               leftIndent=12,
                                               bulletIndent=6)
        self['Error'] = styles.ParagraphStyle('Error',
                                              parent=self['Answer'],
                                              backColor='yellow')
        # Generate the inline versions of these, which use a bullet
        # for the text of the actual question, and indent appropriately
        for sheet in ('Question', 'Subquestion'):
            name = 'Inline' + sheet
            self[name] = styles.ParagraphStyle(
                name, parent=self[sheet],
                bulletIndent=self[sheet].leftIndent,
                bulletFontName=self[sheet].fontName,
                bulletFontSize=self[sheet].fontSize,
                leftIndent=(self[sheet].leftIndent *
                            1.5) + self['Answer'].leftIndent,
                leading=self['Answer'].leading,
                fontName=self['Answer'].fontName)
        # For each of the sheets, generate a version with these 3 suffixes,
        # to allow items to be concatenated.  This is primarily for questions
        # with embedded newlines.
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


class Section:
    def __init__(self, title, **kwargs):
        self.title = title
        self.inline_single_answers = []
        self.skip_question_numbers = False
        self.skip_footer = False

    def __repr__(self):
        return "Section({0},numbers={1},footer={2})\n  {3}".format(
            self.title,
            self.skip_question_numbers,
            self.skip_footer,
            self.inline_single_answers)

class SectionStart(NullDraw):
    def __init__(self, section, callback):
        NullDraw.__init__(self)
        self._section = section
        self._callback = callback

    def draw(self):
        self._callback(self._section)

class PDF(SimpleDocTemplate):
    def __init__(self, filename):
        # Sigh.  SimpleDocTemplate is an old-style class
        SimpleDocTemplate.__init__(self, filename,
                                   pagesize=pagesizes.letter)
        self.stylesheet = StyleSheet()
        self.header_lines = []
        self._this_section = Section('Untitled')
        # Start with a Spacer for the header on the first page
        self.story = [Spacer(1, 1.5 * units.inch)]
        self.leftMargin = 0.5 * units.inch
        self.rightMargin = self.leftMargin
        self.topMargin = 0.5 * units.inch
        self.bottomMargin = 0.75 * units.inch
        # Record the width and height now, because in the build stage
        # width and height are set to the area inside the margins
        (self.page_w, self.page_h) = pagesizes.letter

    def _scoring_table(self, canvas, data, **kwargs):
        row_height = kwargs.get('row_height', None)
        col_width = kwargs.get('col_width', None)
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
        for row,txt in enumerate(self.header_lines, start=1):
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
        # This gets called at the start of a page, not the end.
        canvas.saveState()
        canvas.setFont('Helvetica', 10)
        canvas.drawString(0.5 * units.inch,
                          0.5 * units.inch,
                          'Page {0}'.format(self.page))
        canvas.restoreState()

    def _add_section_footer(self, end_section=False):
        if self._this_section.skip_footer:
            return
        canvas = self.canv
        canvas.saveState()
        y = 0.5 * units.inch
        if not end_section:
            x = self.page_w - (0.5 * units.inch)
            font = ('Helvetica-Oblique', 10)
            canvas.setFont(*font)
            canvas.drawRightString(x, y,
                                   '(section continues on next page)')
        else:
            x = self.page_w - (0.75 * units.inch)
            font = ('Helvetica', 10)
            canvas.setFont(*font)
            canvas.drawRightString(x, y, ' score: ')
            x -= stringWidth(' score: ', *font)
            font = ('Helvetica-Oblique', 10)
            canvas.setFont(*font)
            canvas.drawRightString(x, y, self._this_section.title)
            canvas.line(self.page_w - (0.75 * units.inch),
                        y,
                        self.page_w - (0.5 * units.inch),
                        y)
        canvas.restoreState()
        self._footer_printed = True

    def handle_pageBreak(self):
        self._add_section_footer(end_section=True)
        SimpleDocTemplate.handle_pageBreak(self)

    def handle_pageBegin(self):
        self._footer_printed = False
        SimpleDocTemplate.handle_pageBegin(self)

    def handle_pageEnd(self):
        if not self._footer_printed:
            self._add_section_footer()
        SimpleDocTemplate.handle_pageEnd(self)

    def _set_current_section(self, section):
        self._this_section = section

    def add_section(self, section):
        self._this_section = section
        self.story.append(SectionStart(section,
                                       self._set_current_section))

    def add_page_title(self, text):
        self.add_paragraph(text, style='Title')

    def can_inline_question(self, question):
        if ((question.type == 'open_ended/single') and
            (question.heading in self._this_section.inline_single_answers) and
            self._will_fit_inline(question.heading,
                                  'InlineQuestion')):
            return True
        return False

    def add_question_response(self, response):
        question_heading = u'{0}. {1}'.format(response.position,
                                              response.heading)
        if self._this_section.skip_question_numbers:
            question_heading = response.heading
        if not response:
            self.add_paragraph(question_heading, style='Question')
            if response.subheadings() is not None:
                [self.add_paragraph('(no response)',
                                    style='InlineSubquestion',
                                    bulletText=subhead) for subhead
                 in response.subheadings()]
            else:
                self.add_paragraph('(no response)', style='Answer')
            return
        if self.can_inline_question(response):
            self.add_paragraph(response.answer[0], style='InlineQuestion',
                               bulletText=question_heading)
        else:
            self.add_paragraph(question_heading, style='Question')
            bullet = u"\u2022" if response.type.family == 'multiple_choice' \
                else u''
            for a in response.answer:
                if isinstance(a, tuple):
                    self.add_paragraph(
                        '(no response)' if a[1] is None else a[1],
                        style='InlineSubquestion',
                        bulletText=a[0])
                else:
                    self.add_paragraph(a, style='Answer',
                                       bulletText=bullet)
                    
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
        self.story.append(PageBreak())

    def save(self):
        self.build(self.story,
                   onFirstPage=self._header,
                   onLaterPages=self._footer)

