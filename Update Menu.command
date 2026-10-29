#!/bin/zsh
# Double-click on macOS, or pass updater options from Terminal.
cd -- "${0:A:h}" || exit 1

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

"$PYTHON" scripts/update.py "$@"
result_code=$?

if [[ $result_code -eq 0 ]]; then
  printf '\n✓ Menu update completed successfully!\n'
  printf 'Open index.html in your browser to view the latest menu.\n\n'
else
  printf '\n✗ Menu update failed. See the message above.\n\n'
fi

if [[ -t 0 ]]; then
  printf 'Press Enter to close this window… '
  read -r _
fi

exit $result_code

