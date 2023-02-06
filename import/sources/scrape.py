#!/usr/bin/env python3

LOAD_TIME=0.8

import os
import chromedriver_binary
from selenium import webdriver
import sys
import time
import urllib.parse


from webdriver_manager.chrome import ChromeDriverManager
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

driver.get('https://avinor.no/en/ais/aipnorway/')

time.sleep(LOAD_TIME)

buttons = driver.find_elements_by_xpath('//button')
for x in buttons:
    if x.text == "Accept":
        x.click()
        break

time.sleep(LOAD_TIME)

links = driver.find_elements_by_xpath('//a')
for x in links:
    if x.text == "Open AIP Norway":
        x.click()
        break

time.sleep(LOAD_TIME)

with open('sources.list', 'r') as src:
    for line in src.readlines():
        if len(line)>0:
            ctrl = line[0]
            if ctrl != "=" and ctrl != "T":
                continue
            line = line[1:].strip()
            print(f"Fetching {line}")

            driver.get(line)
            time.sleep(LOAD_TIME)

            fname = urllib.parse.quote(line, safe="")

            with open(f'pdf/{fname}', 'w') as f:
                f.write(driver.page_source)
                if ctrl=="=":
                    os.system(f"./layout-2.sh {fname}")
                if ctrl=="T":
                    os.system(f"./layout-3.sh {fname}")


driver.close()
