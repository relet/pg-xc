#!/usr/bin/env python3

LOAD_TIME=0.8
HEADLESS=False

import os
from selenium import webdriver
import time
import urllib.parse
import chromedriver_binary
from selenium.webdriver.support import ui
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import sys


options = webdriver.chrome.options.Options()
if HEADLESS:
  options.add_argument('--headless')

from selenium.webdriver.chrome.service import Service as ChromeService

# fix chrome version until updates are available
driver = webdriver.Chrome(service=ChromeService('/usr/bin/chromedriver'))


driver.get('https://avinor.no/en/ais/aipnorway/')

time.sleep(LOAD_TIME)

buttons = driver.find_elements(By.XPATH, '//button')
for x in buttons:
    if x.text == "Accept":
        x.click()
        break

time.sleep(LOAD_TIME)

links = driver.find_elements(By.XPATH, '//a')
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
