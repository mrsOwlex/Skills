#!/bin/sh

# render-diff.sh — emit a complete, HTML-escaped <pre class="diff"> block for ONE file.
#
# Usage (run inside the repository being reviewed):
#   render-diff.sh BASE_REF PATH
#
# It runs `git diff --find-renames BASE_REF...HEAD -- PATH` and renders EVERY line as
# <span class="ln CLASS">...</span>, escaping & < >. Line classes match the dashboard
# theme: hh (hunk header), meta (file/index/rename headers), add, del, ctx.
#
# The point is determinism: the agent never transcribes or abbreviates diff text by hand.
# It calls this helper per changed file and embeds the output verbatim inside the file's
# collapsible <details>. This guarantees the FULL diff is present and correctly escaped.
#
# For a deleted file, pass the same PATH; git still produces the removal diff against
# BASE_REF...HEAD. If the diff is empty (e.g. pure rename with no content change) the
# block contains a single note line.

set -u

PROGRAM=${0##*/}

if [ "$#" -ne 2 ]; then
  printf "Usage: %s BASE_REF PATH\n" "$PROGRAM" >&2
  exit 2
fi

BASE_REF=$1
FILE=$2

diff_text=$(git diff --find-renames "$BASE_REF"...HEAD -- "$FILE" 2>/dev/null)

# Derive a language hint for the dashboard's syntax highlighter from the file name:
# the lowercased extension, or the lowercased basename when there is no extension
# (Dockerfile, Makefile, ...). The highlighter maps unknown values to "no highlight".
base=${FILE##*/}
case "$base" in
  *.*) lang=${base##*.} ;;
  *)   lang=$base ;;
esac
lang=$(printf '%s' "$lang" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9')

printf '<pre class="diff" data-lang="%s">' "$lang"

printf "%s\n" "$diff_text" | awk '
function esc(s) {
  gsub(/&/, "\\&amp;", s)
  gsub(/</, "\\&lt;",  s)
  gsub(/>/, "\\&gt;",  s)
  return s
}
BEGIN { real = 0; inhunk = 0 }
length($0) == 0 { next }   # skip the sole empty line produced for an empty diff
{
  real++
  line = $0
  # Track hunk state so that "---"/"+++"/etc. are only treated as file-header
  # metadata BEFORE the first "@@" of a file. Inside a hunk, a "+"/"-" line is
  # always content (e.g. an added "+++" markdown rule must render as add, not meta).
  if (line ~ /^@@/) { cls = "hh"; inhunk = 1 }
  else if (line ~ /^diff /) { cls = "meta"; inhunk = 0 }
  else if (!inhunk && line ~ /^(index |new file|deleted file|rename |copy |similarity |dissimilarity |old mode|new mode|--- |\+\+\+ |Binary )/) cls = "meta"
  else if (substr(line, 1, 1) == "+") cls = "add"
  else if (substr(line, 1, 1) == "-") cls = "del"
  else cls = "ctx"
  printf "<span class=\"ln %s\">%s</span>", cls, esc(line)
}
END {
  if (real == 0) {
    printf "<span class=\"ln meta\">(no textual diff — rename/mode change only)</span>"
  }
}
'

printf '</pre>\n'
