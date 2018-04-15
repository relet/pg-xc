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
  LAYOUT=0
  SKIP=0
  # skip comment lines
  if [[ $p =~ ^# ]]; then continue; fi
  # skip empty lines
  if [ -z "$p" ]; then continue; fi
  # if a line starts with Z, download and unpack a zip archive
  if [[ $p =~ ^Z ]]; then
      FILENAME=$(urlencode ${p:2})
      URLNAME=${p:2}
      if [ ! -e "./zip/$FILENAME" ]; then
          mkdir -p ./zip/$FILENAME
          wget -O "./zip/$FILENAME/archive.zip" "$URLNAME"
          cd zip
          unzip "$FILENAME/archive.zip"
          rm "$FILENAME/archive.zip"
          cd ..
      fi
      continue
  fi

  # otherwise, locate and parse a html
  if [[ $p =~ ^\+ ]]; then
      LAYOUT=2
      SKIP=1
  # or pdf
  elif [[ $p =~ ^.?! ]]; then
      LAYOUT=1
      SKIP=1
  fi
  if [[ $p =~ ^\. ]]; then
      SKIP=$(($SKIP + 1))
  fi
  FILENAME=$(urlencode ${p:$SKIP})
  URLNAME=${p:$SKIP}
  # if a line starts with ., don't try downloading
  if [[ $p =~ ^\. ]]; then
      LOCAL=$(find ./zip/ -name "*${FILENAME}.pdf")
      ARCHIVE_URL=$(echo $LOCAL|awk -F "/" '{print $3}') # get third path after ./ and zip/
      cd "./zip/$ARCHIVE_URL"
      FILENAME=$(find . -name "*${FILENAME}.pdf")
      FILENAME=$(urlencode "${FILENAME#./}")
      cd ../..
      FILENAME="${ARCHIVE_URL}%23${FILENAME}"
      cp "$LOCAL" ./pdf/$FILENAME
  elif [ ! -e "./pdf/$FILENAME" ]; then
      wget -O "./pdf/$FILENAME" "$URLNAME"
  fi

  echo "Processing $FILENAME."
  if [ $LAYOUT = 2 ]; then
      mv "./pdf/$FILENAME" "./pdf/$FILENAME.html"
      lynx -dump "./pdf/$FILENAME.html" > "./txt/$FILENAME.txt"
  elif [ $LAYOUT = 1 ]; then
      pdftotext -layout "./pdf/$FILENAME" "./txt/$FILENAME.txt"
  else
      pdftotext "./pdf/$FILENAME" "./txt/$FILENAME.txt"
  fi
done < sources.list
