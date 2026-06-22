#!/bin/sh

set -u

PROGRAM=${0##*/}
OUTPUT_ROOT="${HOME}/.ai-reviews/mr-human-review-dashboard"

usage() {
  cat >&2 <<EOF
Usage:
  $PROGRAM prepare [--harness VALUE] [--model VALUE] [--review NUMBER_OR_URL]
  $PROGRAM open OUTPUT_PATH
EOF
}

shell_quote() {
  printf "'"
  printf "%s" "$1" | sed "s/'/'\\\\''/g"
  printf "'"
}

emit() {
  key=$1
  value=$2
  printf "%s=" "$key"
  shell_quote "$value"
  printf "\n"
}

die() {
  printf "%s: %s\n" "$PROGRAM" "$*" >&2
  exit 1
}

warn() {
  printf "%s: warning: %s\n" "$PROGRAM" "$*" >&2
}

slugify() {
  input=$1
  max_len=$2
  fallback=$3

  if command -v iconv >/dev/null 2>&1; then
    ascii=$(printf "%s" "$input" | iconv -c -t 'ASCII//TRANSLIT' 2>/dev/null || printf "%s" "$input")
  else
    ascii=$input
  fi

  slug=$(printf "%s" "$ascii" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9][^a-z0-9]*/-/g; s/^-//; s/-$//' \
    | cut -c "1-${max_len}" \
    | sed 's/-$//')

  if [ -z "$slug" ]; then
    slug=$fallback
  fi

  printf "%s" "$slug"
}

remote_path() {
  url=$1
  clean=$(printf "%s" "$url" | sed 's/[.]git$//')

  case "$clean" in
    git@*:*)
      path=${clean#*:}
      ;;
    *://*)
      path=$(printf "%s" "$clean" | sed 's#^[A-Za-z][A-Za-z0-9+.-]*://[^/]*/*##')
      ;;
    *)
      path=$clean
      ;;
  esac

  printf "%s" "$path"
}

remote_platform() {
  url=$1
  case "$url" in
    *github.com*) printf "github" ;;
    *gitlab.com*) printf "gitlab" ;;
    *) printf "" ;;
  esac
}

first_remote_url() {
  url=$(git remote get-url origin 2>/dev/null || true)
  if [ -n "$url" ]; then
    printf "%s" "$url"
    return
  fi

  remotes=$(git remote 2>/dev/null || true)
  for remote in $remotes; do
    url=$(git remote get-url "$remote" 2>/dev/null || true)
    if [ -n "$url" ]; then
      printf "%s" "$url"
      return
    fi
  done
}

resolve_base_ref() {
  name=$1

  case "$name" in
    origin/*)
      candidates=$name
      ;;
    "")
      return 1
      ;;
    *)
      candidates="origin/$name $name"
      ;;
  esac

  for candidate in $candidates; do
    if git rev-parse --verify --quiet "$candidate^{commit}" >/dev/null 2>&1; then
      printf "%s" "$candidate"
      return 0
    fi
  done

  return 1
}

fallback_base_ref() {
  tried=""
  for candidate in origin/main main origin/master master; do
    if [ -z "$tried" ]; then
      tried=$candidate
    else
      tried="$tried, $candidate"
    fi
    if git rev-parse --verify --quiet "$candidate^{commit}" >/dev/null 2>&1; then
      printf "%s" "$candidate"
      return 0
    fi
  done

  printf "%s" "$tried" >&2
  return 1
}

gh_review_info() {
  branch=$1
  review_ref=$2

  command -v gh >/dev/null 2>&1 || return 1

  template='{{.number}}{{"\n"}}{{.title}}{{"\n"}}{{.url}}{{"\n"}}{{.baseRefName}}{{"\n"}}'

  if [ -n "$review_ref" ]; then
    if gh pr view "$review_ref" --json number,title,url,baseRefName --template "$template" 2>/dev/null; then
      return 0
    fi
    return 1
  fi

  if [ -n "$branch" ] && [ "$branch" != "HEAD" ]; then
    count=$(gh pr list --head "$branch" --state open --json number --jq 'length' 2>/dev/null || printf "0")

    if [ "$count" -gt 1 ]; then
      list_template='{{range .}}#{{.number}} {{.title}} -> {{.baseRefName}} {{.url}}{{"\n"}}{{end}}'
      candidates=$(gh pr list --head "$branch" --state open --json number,title,url,baseRefName --template "$list_template" 2>/dev/null || true)
      printf "%s\n" "$candidates" >&2
      return 2
    fi

    if [ "$count" -eq 1 ]; then
      if gh pr list --head "$branch" --state open --json number,title,url,baseRefName --template '{{range .}}{{.number}}{{"\n"}}{{.title}}{{"\n"}}{{.url}}{{"\n"}}{{.baseRefName}}{{"\n"}}{{end}}' 2>/dev/null; then
        return 0
      fi
      return 1
    fi
  fi

  if gh pr view --json number,title,url,baseRefName --template "$template" 2>/dev/null; then
    return 0
  fi
  return 1
}

json_string_value() {
  key=$1
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" | sed 's/\\u0026/\&/g; s/\\"/"/g'
}

json_number_value() {
  key=$1
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\\([0-9][0-9]*\\).*/\\1/p"
}

glab_review_info() {
  branch=$1
  review_ref=$2

  command -v glab >/dev/null 2>&1 || return 1

  if [ -n "$review_ref" ]; then
    json=$(glab mr view "$review_ref" --output json 2>/dev/null || true)
  else
    if [ -n "$branch" ] && [ "$branch" != "HEAD" ]; then
      list_json=$(glab mr list --source-branch "$branch" --state opened --output json 2>/dev/null || true)
      count=$(printf "%s" "$list_json" | grep -o '"iid"[[:space:]]*:' | wc -l | tr -d ' ')
      if [ "$count" -eq 0 ]; then
        count=$(printf "%s" "$list_json" | grep -o '"id"[[:space:]]*:' | wc -l | tr -d ' ')
      fi

      if [ "$count" -gt 1 ]; then
        printf "%s\n" "$list_json" >&2
        return 2
      fi

      if [ "$count" -eq 1 ]; then
        json=$list_json
      else
        json=$(glab mr view --output json 2>/dev/null || true)
      fi
    else
      json=$(glab mr view --output json 2>/dev/null || true)
    fi
  fi

  [ -n "$json" ] || return 1

  number=$(printf "%s" "$json" | json_number_value iid)
  if [ -z "$number" ]; then
    number=$(printf "%s" "$json" | json_number_value id)
  fi
  title=$(printf "%s" "$json" | json_string_value title)
  url=$(printf "%s" "$json" | json_string_value web_url)
  if [ -z "$url" ]; then
    url=$(printf "%s" "$json" | json_string_value webUrl)
  fi
  base=$(printf "%s" "$json" | json_string_value target_branch)
  if [ -z "$base" ]; then
    base=$(printf "%s" "$json" | json_string_value targetBranch)
  fi

  [ -n "$number$title$url$base" ] || return 1
  printf "%s\n%s\n%s\n%s\n" "$number" "$title" "$url" "$base"
}

parse_review_block() {
  block=$1

  REVIEW_NUMBER=$(printf "%s\n" "$block" | sed -n '1p')
  REVIEW_TITLE=$(printf "%s\n" "$block" | sed -n '2p')
  REVIEW_URL=$(printf "%s\n" "$block" | sed -n '3p')
  REVIEW_BASE=$(printf "%s\n" "$block" | sed -n '4p')
}

reserve_output_path() {
  dir=$1
  prefix=$2
  review_slug=$3
  timestamp=$4

  mkdir -p "$dir" || die "could not create output directory: $dir"

  n=1
  while :; do
    if [ "$n" -gt 1000 ]; then
      die "could not reserve output path after 1000 attempts in $dir"
    fi

    if [ "$n" -eq 1 ]; then
      candidate="$dir/${prefix}${review_slug}-${timestamp}.html"
    else
      candidate="$dir/${prefix}${review_slug}-${timestamp}-$n.html"
    fi

    if ( set -C; : > "$candidate" ) 2>/dev/null; then
      printf "%s" "$candidate"
      return 0
    fi

    if [ ! -e "$candidate" ]; then
      die "could not reserve output path: $candidate"
    fi

    n=$((n + 1))
  done
}

prepare() {
  HARNESS=unknown
  MODEL=unknown
  REVIEW_REF=

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --harness)
        [ "$#" -ge 2 ] || die "--harness requires a value"
        HARNESS=$2
        shift 2
        ;;
      --model)
        [ "$#" -ge 2 ] || die "--model requires a value"
        MODEL=$2
        shift 2
        ;;
      --review)
        [ "$#" -ge 2 ] || die "--review requires a value"
        REVIEW_REF=$2
        shift 2
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        die "unknown argument for prepare: $1"
        ;;
    esac
  done

  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a Git repository"
  cd "$REPO_ROOT" || die "could not enter repository root: $REPO_ROOT"

  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || true)
  if [ -z "$CURRENT_BRANCH" ]; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || printf "HEAD")
  fi

  HEAD_SHA=$(git rev-parse HEAD 2>/dev/null) || die "could not resolve HEAD"
  REMOTE_URL=$(first_remote_url)
  PLATFORM=$(remote_platform "$REMOTE_URL")

  if [ -n "$REMOTE_URL" ]; then
    raw_repo=$(remote_path "$REMOTE_URL")
  else
    raw_repo=${REPO_ROOT##*/}
  fi
  REPO_SLUG=$(slugify "$raw_repo" 120 "repo")

  REVIEW_NUMBER=
  REVIEW_TITLE=
  REVIEW_URL=
  REVIEW_KIND=
  REVIEW_BASE=

  gh_err=$(mktemp "${TMPDIR:-/tmp}/mr-human-review-gh.XXXXXX") || die "could not create temporary file"
  trap 'rm -f "$gh_err"' EXIT HUP INT TERM
  gh_status=1
  gh_block=$(gh_review_info "$CURRENT_BRANCH" "$REVIEW_REF" 2>"$gh_err")
  gh_status=$?
  if [ "$gh_status" -eq 2 ]; then
    printf "%s: multiple GitHub pull requests match this branch. Ask the user which one to use, then rerun with --review.\n" "$PROGRAM" >&2
    cat "$gh_err" >&2
    rm -f "$gh_err"
    exit 2
  fi
  rm -f "$gh_err"
  trap - EXIT HUP INT TERM

  if [ "$gh_status" -eq 0 ] && [ -n "$gh_block" ]; then
    parse_review_block "$gh_block"
    PLATFORM=github
    REVIEW_KIND=pull_request
  else
    glab_err=$(mktemp "${TMPDIR:-/tmp}/mr-human-review-glab.XXXXXX") || die "could not create temporary file"
    trap 'rm -f "$glab_err"' EXIT HUP INT TERM
    glab_block=$(glab_review_info "$CURRENT_BRANCH" "$REVIEW_REF" 2>"$glab_err")
    glab_status=$?
    if [ "$glab_status" -eq 2 ]; then
      printf "%s: multiple GitLab merge requests match this branch. Ask the user which one to use, then rerun with --review.\n" "$PROGRAM" >&2
      cat "$glab_err" >&2
      rm -f "$glab_err"
      exit 2
    fi
    rm -f "$glab_err"
    trap - EXIT HUP INT TERM

    if [ "$glab_status" -eq 0 ] && [ -n "$glab_block" ]; then
      parse_review_block "$glab_block"
      PLATFORM=gitlab
      REVIEW_KIND=merge_request
    fi
  fi

  BASE_REF=
  BASE_TRIED=
  if [ -n "$REVIEW_BASE" ]; then
    BASE_REF=$(resolve_base_ref "$REVIEW_BASE" || true)
    BASE_TRIED="origin/$REVIEW_BASE, $REVIEW_BASE"
  fi

  if [ -z "$BASE_REF" ]; then
    fallback_err=$(fallback_base_ref 2>&1)
    if [ $? -eq 0 ]; then
      BASE_REF=$fallback_err
      BASE_TRIED="origin/main, main, origin/master, master"
    else
      if [ -n "$BASE_TRIED" ]; then
        BASE_TRIED="$BASE_TRIED, $fallback_err"
      else
        BASE_TRIED=$fallback_err
      fi
      die "could not resolve a base ref. Tried: $BASE_TRIED"
    fi
  fi

  BASE_SHA=$(git rev-parse "$BASE_REF^{commit}" 2>/dev/null) || die "could not resolve base SHA for $BASE_REF"

  git diff --quiet "$BASE_REF"...HEAD --
  diff_status=$?
  if [ "$diff_status" -eq 0 ]; then
    die "no changes to review against $BASE_REF"
  fi
  if [ "$diff_status" -ne 1 ]; then
    die "could not compute diff against $BASE_REF"
  fi

  if [ -z "$REVIEW_TITLE" ]; then
    if [ -n "$CURRENT_BRANCH" ] && [ "$CURRENT_BRANCH" != "HEAD" ]; then
      REVIEW_TITLE=$CURRENT_BRANCH
    else
      REVIEW_TITLE=$(git log -1 --format=%s 2>/dev/null || printf "review")
    fi
  fi

  if [ -n "$REVIEW_TITLE" ]; then
    raw_review=$REVIEW_TITLE
  else
    raw_review=review
  fi
  REVIEW_SLUG=$(slugify "$raw_review" 80 "review")

  prefix=
  if [ -n "$REVIEW_NUMBER" ]; then
    case "$REVIEW_KIND" in
      pull_request) prefix="pr-$REVIEW_NUMBER-" ;;
      merge_request) prefix="mr-$REVIEW_NUMBER-" ;;
    esac
  fi

  CREATED_AT=$(date '+%Y-%m-%d-%H%M%S')
  OUTPUT_DIR="$OUTPUT_ROOT/$REPO_SLUG"
  OUTPUT_PATH=$(reserve_output_path "$OUTPUT_DIR" "$prefix" "$REVIEW_SLUG" "$CREATED_AT") || die "could not reserve output path"

  emit BASE_REF "$BASE_REF"
  emit BASE_SHA "$BASE_SHA"
  emit CURRENT_BRANCH "$CURRENT_BRANCH"
  emit HEAD_SHA "$HEAD_SHA"
  emit REPO_ROOT "$REPO_ROOT"
  emit REPO_SLUG "$REPO_SLUG"
  emit REVIEW_TITLE "$REVIEW_TITLE"
  emit REVIEW_KIND "$REVIEW_KIND"
  emit REVIEW_NUMBER "$REVIEW_NUMBER"
  emit REVIEW_URL "$REVIEW_URL"
  emit PLATFORM "$PLATFORM"
  emit OUTPUT_PATH "$OUTPUT_PATH"
  emit OUTPUT_DIR "$OUTPUT_DIR"
  emit CREATED_AT "$CREATED_AT"
  emit HARNESS "$HARNESS"
  emit MODEL "$MODEL"
}

open_report() {
  [ "$#" -eq 1 ] || die "open requires exactly one OUTPUT_PATH argument"
  target=$1

  case "$target" in
    "$OUTPUT_ROOT"/*)
      ;;
    *)
      die "refusing to open path outside $OUTPUT_ROOT: $target"
      ;;
  esac

  [ -f "$target" ] || die "report does not exist: $target"
  [ -s "$target" ] || die "report is empty: $target"

  if command -v open >/dev/null 2>&1; then
    open "$target" >/dev/null 2>&1 || warn "could not open report with open: $target"
    exit 0
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$target" >/dev/null 2>&1 || warn "could not open report with xdg-open: $target"
    exit 0
  fi

  if command -v wslview >/dev/null 2>&1; then
    wslview "$target" >/dev/null 2>&1 || warn "could not open report with wslview: $target"
    exit 0
  fi

  if command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    win_path=$(wslpath -w "$target" 2>/dev/null || true)
    if [ -n "$win_path" ]; then
      cmd.exe /c start "" "$win_path" >/dev/null 2>&1 || warn "could not open report with cmd.exe: $target"
      exit 0
    fi
  fi

  warn "no supported browser opener found for $target"
  exit 0
}

if [ "$#" -lt 1 ]; then
  usage
  exit 1
fi

mode=$1
shift

case "$mode" in
  prepare)
    prepare "$@"
    ;;
  open)
    open_report "$@"
    ;;
  --help|-h)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
