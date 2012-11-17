#!/bin/sh
set -v

mkdir -p $HOME/.local/share/gedit/plugins/gedit_ruby_syntax_checker
cp -r gedit_ruby_syntax_checker $HOME/.local/share/gedit/plugins/.
cp gedit_ruby_syntax_checker.plugin $HOME/.local/share/gedit/plugins/.
