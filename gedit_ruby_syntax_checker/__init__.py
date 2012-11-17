#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""gedit_ruby_syntax_checker : A plugin for gedit
   to display error and warning from ruby interpreter."""

__author__ = "Rubén Caro"
__copyright__ = "Copyright 2012 " + __author__
__license__ = "GPLv3"
__version__ = "0.1"
__maintainer__ = "Rubén Caro"
__email__ = "ruben.caro@lanuez.org"
__status__ = "Beta"

try:
    from gi.repository import GObject, Gedit, Gtk, Pango
except ImportError, err:
    print 'This plugin needs to be launched by GEdit 3'
    print err

import re
from subprocess import Popen, PIPE
import threading


def apply_style(style, tag):
    """Apply a style to a tag from the default theme style
       This lightly modified code come from the synctext.py gedit plugin"""

    def apply_style_prop(tag, style, prop):
        if style.get_property(prop + "-set"):
            tag.set_property(prop, style.get_property(prop))
        else:
            tag.set_property(prop, None)

    def apply_style_prop_bool(tag, style, prop, whentrue, whenfalse):
        if style.get_property(prop + "-set"):
            prop_value = whentrue if style.get_property(prop) else whenfalse
            tag.set_property(prop, prop_value)

    apply_style_prop(tag, style, "foreground")
    apply_style_prop(tag, style, "background")

    try:
        apply_style_prop_bool(tag,
                              style,
                              "weight",
                              Pango.Weight.BOLD,
                              Pango.Weight.NORMAL)
    except TypeError, err:
        #Different version of gtk 3 have different properties ... :(
        print err

    apply_style_prop_bool(tag,
                          style,
                          "italic",
                          Pango.Style.ITALIC,
                          Pango.Style.NORMAL)
    apply_style_prop_bool(tag,
                          style,
                          "underline",
                          Pango.Underline.SINGLE,
                          Pango.Underline.NONE)
    apply_style_prop(tag, style, "strikethrough")


class Message(object):

    def __init__(self, document, lineno, column, message):

        self._doc = document

        self._lineno = lineno
        self._column = column
        self._message = message

        self._start_iter = None
        self._end_iter = None

        self._stock_id = self._get_stock_id(message)

    def _get_stock_id(self, message):

        if message.startswith('E'):
            return Gtk.STOCK_DIALOG_ERROR

        elif message.startswith('W'):
            return Gtk.STOCK_DIALOG_WARNING

        elif message.startswith('C'):
            return Gtk.STOCK_DIALOG_INFO

        else:
            return Gtk.STOCK_DIALOG_INFO

    def setWordBounds(self, start, end):
        self._start_iter = start
        self._end_iter = end

    doc = property(lambda self: self.__doc)

    lineno = property(lambda self: self._lineno)
    column = property(lambda self: self._lineno)
    message = property(lambda self: self._message)

    start = property(lambda self: self._start_iter)
    end = property(lambda self: self._end_iter)

    stock_id = property(lambda self: self._stock_id)


class ResultsModel(Gtk.ListStore):

    def __init__(self):
        super(ResultsModel, self).__init__(int, int, str)

    def add(self, msg):
        self.append([msg.lineno, msg.column, msg.message])


class ResultsView(Gtk.TreeView):

    def __init__(self, panel):
        super(ResultsView, self).__init__()

        self._panel = panel

        linha = Gtk.TreeViewColumn("Line")
        linha_cell = Gtk.CellRendererText()
        linha.pack_start(linha_cell, True)
        linha.add_attribute(linha_cell, 'text', 0)
        linha.set_sort_column_id(0)
        self.append_column(linha)

        msgtype = Gtk.TreeViewColumn("Column")
        msgtype_cell = Gtk.CellRendererText()
        msgtype.pack_start(msgtype_cell, True)
        msgtype.add_attribute(msgtype_cell, 'text', 1)
        msgtype.set_sort_column_id(1)
        self.append_column(msgtype)

        msg = Gtk.TreeViewColumn("Message")
        msg_cell = Gtk.CellRendererText()
        msg.pack_start(msg_cell, True)
        msg.add_attribute(msg_cell, 'text', 2)
        msg.set_sort_column_id(2)
        self.append_column(msg)

        self.connect("row-activated", self._row_activated_cb)

    def _row_activated_cb(self, view, row, column):
        model = view.get_model()
        iter = model.get_iter(row)

        window = self._panel.get_window()

        document = window.get_active_document()
        line = model.get_value(iter, 0) - 1
        document.goto_line(line)

        view = window.get_active_view()

        text_iter = document.get_iter_at_line(line)
        view.scroll_to_iter(text_iter, 0.25, False, 0.5, 0.5)
        view.grab_focus()


class ResultsPanel(Gtk.ScrolledWindow):

    def __init__(self, window):

        super(ResultsPanel, self).__init__()

        self.window = window
        self.view = ResultsView(self)
        self.add(self.view)
        self.view.show()

    def set_model(self, model):
        self.view.set_model(model)

    def get_window(self):
        return self.window


class RubySyntaxCheckerPlugin(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = "RubySyntaxChecker"

    window = GObject.property(type=Gedit.Window)
    panel = GObject.property(type=Gedit.Panel)
    documents = []
    _errors_tag = {}
    _results = {}
    _errors = {}

    def __init__(self):
        GObject.Object.__init__(self)

    def do_activate(self):
        self._insert_panel()
        self.window.connect("tab-added", self.on_tab_added)
        self.window.connect("tab-removed", self.on_tab_removed)

    def do_deactivate(self):
        self._remove_panel()

    def on_notify_style_scheme(self, document, param_object):
        style = document.get_style_scheme().get_style('def:error')
        apply_style(style, self._errors_tag[document])

    def _insert_panel(self):
        """Insert bottom GEdit panel"""
        self._panel = ResultsPanel(self.window)

        image = Gtk.Image()
        image.set_from_icon_name('gnome-mime-text-x-python',
                                 Gtk.IconSize.MENU)

        bottom_panel = self.window.get_bottom_panel()
        bottom_panel.add_item(self._panel,
                              'ResultsPanel',
                              'RubySyntaxChecker Results',
                              image)

    def _remove_panel(self):
        """Remove the inserted panel from GEdit"""
        bottom_panel = self.window.get_bottom_panel()
        bottom_panel.remove_item(self._panel)

    def on_tab_added(self, window, tab):
        """Initialize the required vars"""
        document = tab.get_document()

        self._results[document] = ResultsModel()
        self._errors[document] = []
        document.connect('loaded', self.analyse)
        document.connect('saved', self.analyse)
        document.connect('cursor-moved', self.display_error_msg)
        self._add_tags(document)

    def on_tab_removed(self, window, tab):
        """Cleaning results not needed anymore"""
        document = tab.get_document()
        if document in self._results:
            self._results[document] = None
            del self._results[document]

            self._errors[document] = None
            del self._errors[document]

            self._remove_tags(document)

    def _add_tags(self, document):
        """Register new tags in the sourcebuffer"""
        style = document.get_style_scheme().get_style('def:error')

        self._errors_tag[document] = \
            document.create_tag("ruby-error",
                                underline=Pango.Underline.ERROR)
        apply_style(style, self._errors_tag[document])

    def _remove_tags(self, document):
        """Remove not anymore used tags"""
        if document in self._errors_tag:
            start, end = document.get_bounds()
            document.remove_tag(self._errors_tag[document], start, end)

    def _highlight_errors(self, errors):
        """Colorize error in the sourcebuffer"""
        document = self.window.get_active_document()

        for err in errors:

            start = document.get_iter_at_line(err.lineno - 1)

            end = document.get_iter_at_line(err.lineno - 1)
            end.forward_to_line_end()

            # apply tag to entire line
            document.apply_tag(self._errors_tag[document], start, end)

    def display_error_msg(self, document):
        """Display a statusbar message if the current line have errors"""
        if document is None:
            return True

        try:
            if document.get_language().get_name() == 'Ruby':
                curline = document.get_iter_at_mark(
                    document.get_insert()).get_line() + 1
                for err in self._errors[document]:
                    if err.lineno == curline:
                        statusbar = self.window.get_statusbar()
                        statusbar_ctxtid = statusbar.get_context_id('RubySyntaxChecker')
                        statusbar.push(statusbar_ctxtid, 'Line : %s : %s'
                                       % (err.lineno, err.message))
        except AttributeError:
            #document.get_language return None
            #No language define so nothing to do
            pass

        return True

    def analyse(self, document, option):
        """Launch a gedit_ruby_syntax_checker process and populate vars"""
        if document is None:
            return True

        try:
            if document.get_language().get_name() != 'Ruby':
                return True
        except AttributeError:
            return True

        threading.Thread(target=self._run_ruby_syntax_check, args=(document,)).start()

    def _run_ruby_syntax_check(self, document):
        errors = []
        path = document.get_location().get_path()
        stdout, stderr = Popen(['ruby -c', path],
                               stdout=PIPE, stderr=PIPE).communicate()
        output = stdout if stdout else stderr

        line_format = re.compile(
            '(?P<path>[^:]+):(?P<line>\d+):'
            + '(?P<character>\d+:)?\s(?P<message>.*$)')

        self._remove_tags(document)

        if document not in self._results:
            self._results[document] = ResultsModel()
        else:
            self._results[document].clear()

        if not output:
            statusbar = self.window.get_statusbar()
            statusbar_ctxtid = statusbar.get_context_id('RubySyntaxChecker')
            statusbar.push(statusbar_ctxtid,
                           "No errors found")
            return

        for line in output.splitlines():
            m = line_format.match(line)
            if not m:
                continue
            groups = m.groupdict()
            if groups['character']:
                err = Message(self.window.get_active_document,
                              int(groups['line']),
                              int(groups['character'].strip(':')),
                              groups['message'],)
            else:
                err = Message(self.window.get_active_document,
                              int(groups['line']),
                              0,
                              groups['message'],)
            errors.append(err)
            self._results[document].add(err)

        self._remove_tags(document)
        self._errors[document] = errors
        self._highlight_errors(self._errors[document])
        self._panel.set_model(self._results[document])

        statusbar = self.window.get_statusbar()
        statusbar_ctxtid = statusbar.get_context_id('RubySyntaxChecker')
        if len(errors) > 0:
            statusbar.push(statusbar_ctxtid,
                           'Line : %s : %s'
                           % (errors[0].lineno, errors[0].message))
        else:
            statusbar.push(statusbar_ctxtid,
                           "No errors found")
