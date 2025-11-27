FILENAME=$1

cat "./pdf/$FILENAME" > /tmp/pgxc
hxprune -c "AmdtDeletedAIRAC" /tmp/pgxc > /tmp/pgxc2
hxprune -c "acParams" /tmp/pgxc2 > /tmp/pgxc
hxprune -c "sdParams" /tmp/pgxc > /tmp/pgxc2
mv /tmp/pgxc2 "./pdf/$FILENAME.html"
rm /tmp/pgxc
html2text -nobs -width 999 "./pdf/$FILENAME.html" > "./txt/$FILENAME.txt"
