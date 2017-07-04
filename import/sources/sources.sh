#!/bin/bash

urlencode() {
    # urlencode <string>
    old_lc_collate=$LC_COLLATE
    LC_COLLATE=C

    local length="${#1}"
    for (( i = 0; i < length; i++ )); do
        local c="${1:i:1}"
        case $c in
            [a-zA-Z0-9.~_-]) printf "$c" ;;
            *) printf '%%%02X' "'$c" ;;
        esac
    done

    LC_COLLATE=$old_lc_collate
}

urldecode() {
    # urldecode <string>

    local url_encoded="${1//+/ }"
    printf '%b' "${url_encoded//%/\\x}"
}

while read p; do
  if [[ $p =~ ^# ]]; then continue; fi
  if [ -z "$p" ]; then continue; fi
  if [[ $p =~ ^! ]]; then
      FILENAME=$(urlencode ${p:1})
  else
      FILENAME=$(urlencode $p)
  fi
  if [ ! -e "./pdf/$FILENAME" ]; then
      wget -O "./pdf/$FILENAME" "$p"
  fi
  if [[ $p =~ ^! ]]; then
      pdftotext -layout "./pdf/$FILENAME" "./txt/$FILENAME.txt"
  else
      pdftotext "./pdf/$FILENAME" "./txt/$FILENAME.txt"
  fi
done < sources.list
