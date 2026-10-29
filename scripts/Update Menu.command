#!/bin/zsh
# Double-click on macOS, or pass updater options from Terminal.
SCRIPT_DIR="${0:A:h}"
ROOT_DIR="${SCRIPT_DIR:h}"
cd -- "$ROOT_DIR" || exit 1

printf '\n=========================================\n'
printf '      Aashirwad Menu Updater             \n'
printf '=========================================\n\n'

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif [[ -x "bin/python" ]]; then
  PYTHON="bin/python"
else
  PYTHON="python3"
fi

"$PYTHON" "$SCRIPT_DIR/update.py" --deploy "$@"
result_code=$?

if [[ $result_code -eq 0 ]]; then
  printf '\n✓ Menu update and automatic deployment completed successfully!\n'
  printf 'Live site: https://abhi266raj.github.io/aashirwad_resturant/\n\n'
else
  printf '\n✗ Menu update failed. See the message above.\n\n'
fi

if [[ -t 0 ]]; then
  printf 'Press Enter to close this window… '
  read -r _
fi

exit $result_code


