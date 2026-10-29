#!/bin/zsh
# Double-click on macOS, or pass updater options from Terminal.
cd -- "${0:A:h}" || exit 1
printf '\nUpdating Aashirwad menu…\n\n'
python3 scripts/update.py "$@"
result_code=$?
if [[ $result_code -eq 0 ]]; then
  printf '\nMenu update completed. Open index.html to view it.\n'
else
  printf '\nMenu update failed. See the error above.\n'
fi
if [[ -t 0 ]]; then
  read -k 1 '?Press any key to close this window…'
  printf '\n'
fi
exit $result_code
