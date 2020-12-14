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

process() {
  FILENAME=$1
  LAYOUT=$2

  echo "Processing $FILENAME."
  if [ $LAYOUT = 3 ]; then
      cat "./pdf/$FILENAME" > /tmp/pgxc
      hxprune -c "AmdtDeletedAIRAC" /tmp/pgxc > /tmp/pgxc2
      hxprune -c "acParams" /tmp/pgxc2 > /tmp/pgxc
      hxprune -c "sdParams" /tmp/pgxc > /tmp/pgxc2
      mv /tmp/pgxc2 "./pdf/$FILENAME.html"
      rm /tmp/pgxc
      html2text -width 999 "./pdf/$FILENAME.html" > "./txt/$FILENAME.txt"
  elif [ $LAYOUT = 2 ]; then
      cat "./pdf/$FILENAME" > /tmp/pgxc
      hxprune -c "AmdtDeletedAIRAC" /tmp/pgxc > /tmp/pgxc2
      hxprune -c "acParams" /tmp/pgxc2 > /tmp/pgxc
      hxprune -c "sdParams" /tmp/pgxc > /tmp/pgxc2
      mv /tmp/pgxc2 "./pdf/$FILENAME.html"
      rm /tmp/pgxc
      lynx -dump "./pdf/$FILENAME.html" > "./txt/$FILENAME.txt"
  elif [ $LAYOUT = 1 ]; then
      pdftotext -layout "./pdf/$FILENAME" "./txt/$FILENAME.txt"
  else
      pdftotext "./pdf/$FILENAME" "./txt/$FILENAME.txt"
  fi
}

fromzip() {
  FILENAME=$1

  LOCAL=$(find ./zip/ -name "*${FILENAME}.pdf")
  ARCHIVE_URL=$(echo $LOCAL|awk -F "/" '{print $3}') # get third path after ./ and zip/
  cd "./zip/$ARCHIVE_URL"
  FILENAME=$(find . -name "*${FILENAME}.pdf")
  FILENAME=$(urlencode "${FILENAME#./}")
  cd ../..
  FILENAME="${ARCHIVE_URL}%23${FILENAME}"
  cp "$LOCAL" ./pdf/$FILENAME

  echo "$FILENAME"
}

while read p; do
  LAYOUT=0
  SKIP=0
  STOP=0
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
          cd "zip/$FILENAME"
          unzip "archive.zip"
          rm "archive.zip"
          cd ../..
      fi
      continue
  fi

  # otherwise, locate and parse a html
  if [[ $p =~ ^T ]]; then  # with tables
      LAYOUT=3
      SKIP=1
  elif [[ $p =~ ^\+ ]]; then  # without tables
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
  if [[ $p =~ \*$ ]]; then
      STOP=$(($STOP + 1))
  fi
  SNIPLEN=$((${#p}-$SKIP-$STOP))
  FILENAME=$(urlencode ${p:$SKIP:$SNIPLEN})
  URLNAME=${p:$SKIP}
  # if a line starts with ., don't try downloading
  if [[ $p =~ ^\. ]]; then
      if [[ $p =~ \*$ ]]; then
          find ./zip/ -name "*${FILENAME}??_en.pdf" | while read f
          do
              FILENAME=$(basename "$f")
              echo "Found match in zip $FILENAME";
              FILENAME=$(fromzip "${FILENAME::-4}");
              process $FILENAME $LAYOUT;
          done
          exit 1
      else
          FILENAME=$(fromzip $FILENAME)
          process $FILENAME $LAYOUT
      fi
  elif [ ! -e "./pdf/$FILENAME" ]; then
      curl -b cookies -L --output "./pdf/$FILENAME" "$URLNAME"
      process $FILENAME $LAYOUT
  else
      process $FILENAME $LAYOUT
  fi

done < sources.list
