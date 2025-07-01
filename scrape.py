#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun 29 08:45:02 2025

@author: Feicheiel
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, 
                                        NoSuchElementException, 
                                        ElementClickInterceptedException, 
                                        StaleElementReferenceException, 
                                        WebDriverException
)

from bs4 import BeautifulSoup
import csv
import time
import traceback
import logging

from collections import deque
import re
import os
import pandas as pd

logging.basicConfig(
    filename='nhis_scraper.log',     # Log file name
    filemode='a',                    # 'a' for append, 'w' for overwrite
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO  
)

class NHISScraper: 
    def __init__(self, fln = "nhis_payments.csv", verbose=True, t_wait = 30):
        self.__fln__ = fln
        self.__last_page__ = 0
        self.__verbose__ = verbose #set this to show error messages.

        # LOG / READ
        self.__hashes__ = set()
        self.page_rows = deque()
        if not self.__fln__.endswith(".csv"):
            self.__fln__ = f"{self.__fln__}.csv"
        if not os.path.exists(fln): #Create new file for start of scraping.
            with open(self.__fln__, mode='w', newline="") as log:
                writer = csv.writer(log)
                writer.writerow(["Facility Name", "Category", "District", "Amount Paid", "Claim Month", "Payment Date", "Page", "Hash"])
        else: #Load into memory and resume from the last page
            with open(self.__fln__, mode='r', newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    self.__last_page__ = int(row['Page'])
                    self.__hashes__.add(row['Hash'])
        
        # PATTERNS
        self.__pattern__ = re.compile( 
            r'(?i)(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[\.?\s\-]*(\d{2,4})'
            )
        self.__month_map__ = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        self.__category_patterns__ = {
            r'(?i)\bchps\b': 'CHPS',
            r'(?i)\bpoly\w*': 'Polyclinic',
            r'(?i)\bclinic\w*': 'Clinic',
            r'(?i)\bhealth\b': 'Health Centre',
            r'(?i)\bmedical\b': 'Medical Centre',
            r'(?i)\bhospital\b': 'Hospital',
            r'(?i)\bwellness\b': 'Wellness Centre',
            r'(?i)\bmaternity\b': 'Maternity Home'
        }

        # State holders
        self.__t_wait__ = t_wait
        self.__next_btn_xpath__ = "//button[@title='Next Page']"
        self.__prev_page__ = 0  #Hold a local copy of previous page
        self.__curr_page__ = 0  #Receives the current page count from the webpage presently loaded.
        self.__tot_page_count__ = 0

        # Logs
        self.logger = logging.getLogger(__name__)

        # WEBDRIVER & WEBELEMENTS
        self.__driver__ = webdriver.Safari()
        self.__driver__.set_page_load_timeout(700)
        while True:
            try:
                self.__driver__.get("https://www.nhis.gov.gh/payments")
                self.__getelems__()
                if self.__verbose__:
                    print(f"\033[1;32mPage {self.__curr_page__} Loaded Successfully\033[0m")
                break
            except Exception as e:
                t_wait = 5
                print(f"\033[31mRetrying in {t_wait} seconds due to error: {e} \033[0m")
                time.sleep(t_wait)
    
    def close(self):
        if self.__driver__:
            self.__driver__.quit()
    
    def getClaimsMonth(self, text):
        date_str = ""
        match = self.__pattern__.search(text)
        if match:
            month_str, year_str = match.groups()
            # Normalize month abbreviation
            month_short = month_str[:3].lower()
            month = self.__month_map__[month_short]

            # Normalize year (2-digit to 4-digit)
            year = year_str if len(year_str) == 4 else f"20{year_str.zfill(2)}"

            # Construct date string
            date_str = f"01/{month}/{year}"

        return date_str
    
    def getFacilityCategory(self, name):
        name = name.lower()
        for pattern_, label in self.__category_patterns__.items():
            if re.search(pattern_, name):
                return label
        return "Unknown"
    
    def __getelems__(self):
        """Updates the __curr_page__ and __tot_page_count__"""
        #Extract total page count
        try:
            wait = WebDriverWait(self.__driver__, self.__t_wait__)
            _tot_page_elem_ = wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@class='rgWrap rgInfoPart']/strong[2]"))
            )
            self.__tot_page_count__ = int(_tot_page_elem_.text.strip())
        except Exception as e:
            if self.__verbose__:
                print(f'\033[91m<<Error fetching total page count: {type(e).__name__} — {e}>>')
                self.logger.info(f'\033[91m<<Error fetching total page count: {type(e).__name__} — {e}>>')
        
        #Extract current page
        try:
            wait = WebDriverWait(self.__driver__, self.__t_wait__)
            _cur_page_elem_ = wait.until(
                EC.presence_of_element_located((By.XPATH, "//a[@class='rgCurrentPage']"))
            )
            self.__curr_page__ = int(_cur_page_elem_.text.strip())
        except Exception as e:
            if self.__verbose__:
                print(f'\033[91m<<Error fetching current page number: {type(e).__name__} — {e}>>')
                self.logger.info(f'\033[91m<<Error fetching current page number: {type(e).__name__} — {e}>>')
                traceback.print_exc()

    def __wait_for_page_change(self):
        """
        Helper function used in WebDriverWait to check if page number has changed.
        """
        try:
            self.__getelems__()  # Update self.__curr_page__
            return self.__curr_page__ > self.__prev_page__
        except:
            return False    

    def __goto_next_page__(self):
        #_prev_page_ = self.__prev_page__
        try:
            wait = WebDriverWait(self.__driver__, self.__t_wait__)
            __nxt__ = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@title='Next Page']"))
            )

            if not __nxt__.is_enabled():
                return False

            #self.__driver__.execute_script("arguments[0].scrollIntoView({block: 'center'});", __nxt__)
            self.__driver__.execute_script("arguments[0].click();", __nxt__)

            # Wait till the page number changes before advancing
            WebDriverWait(self.__driver__, self.__t_wait__).until(
                lambda driver: self.__wait_for_page_change()
            )

            self.__getelems__()
            if self.__curr_page__ == self.__prev_page__:
                raise ValueError("Page failed to advance after clicking next.")
            
        except TimeoutException:
            if self.__verbose__:
                print("\033[1;31mTimeout: Next button not found on page.\033[0m")
                self.logger.info("\033[1;31mTimeout: Next button not found on page.\033[0m")
            return False
        
        except Exception as e:
            if self.__verbose__:
                print(f"\033[1;31m<<Click failed", end = ' ')
                print(f"\033[91m[Next Button Error]: {type(e).__name__} — {e}>>\033[0m")
                self.logger.error(f"\033[1;31m<<Click failed")
                self.logger.error(f"\033[91m[Next Button Error]: {type(e).__name__} — {e}>>\033[91m")
                traceback.print_exc()
            return False
        
        self.__prev_page__ = self.__curr_page__ 
        if self.__verbose__:
            print(f'✅ \033[92mSuccessfully jumped to Page: {self.__curr_page__}\033[0m')
            self.logger.info(f'✅ \033[92mSuccessfully jumped to Page: {self.__curr_page__}\033[0m')
        
        return True

    def __jump_to_page__(self, _page_num_, max_attempts=10):
        attempts = 0
        self.__getelems__()
        while (self.__curr_page__ < _page_num_ and attempts < max_attempts):
            if not self.__goto_next_page__():
                break
            attempts += 1

    def __scrape_curr_page__(self):
        
        self.__getelems__()
        success = False
        while not success:
            success = self.__do_scrape__()

        if self.__verbose__ and abs(self.__prev_page__-self.__curr_page__) > 2:
            print(f"\033[31m⛔️ Suspicious jump from page {self.__prev_page__} to {self.__curr_page__}!\033[0m")
            self.logger.warning(f"\033[31m⛔️ Suspicious jump from page {self.__prev_page__} to {self.__curr_page__}!\033[0m")
        self.__prev_page__ = self.__curr_page__
    
    def __do_scrape__(self, t = 2):
        soup = BeautifulSoup(self.__driver__.page_source, 'html.parser')
        table = soup.find('table')

        if not table and self.__verbose__:
            print(f"No table found on page: {self.__prev_page__}")
            self.logger.info(f"No table found on page: {self.__prev_page__}")
            return False

        rows = table.find_all('tr')[1:]
        self.page_rows = deque()

        for tr in rows:
            row = [td.get_text(strip=True) for td in tr.find_all('td')]
            if len(row) == 5 and row[0] != '':
                row[-2] = self.getClaimsMonth(row[-2])
                row.insert(1, self.getFacilityCategory(row[0]))
                row.append(self.__prev_page__)
                # append the hash value
                row.append(f"{str(row[0]).split(' ')[0]}{int(float(row[3])*100)}{''.join(str(row[4]).split('/'))}")
                self.page_rows.append(row)
        
        if not self.page_rows and self.__verbose__:
            print("⚠️ row appears empty or malformed.")
            self.logger.info("⚠️ row appears empty or malformed.")

        else: 
            with open(self.__fln__, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                while(len(self.page_rows)):
                    #for row in self.page_rows:
                    row = self.page_rows.popleft()
                    if row[7] not in self.__hashes__:
                        writer.writerow(row)
                        self.__hashes__.add(row[7])
                    else:
                        continue
            print(f'\033[1;32m✅ Successfully scraped page {self.__prev_page__}/\033[1;37m{self.__tot_page_count__}')
            self.logger.info(f'\033[1;32m✅ Successfully scraped page {self.__prev_page__}/\033[1;37m{self.__tot_page_count__}')
        return True
    
    def scrape(self):

        # Scrape First page
        try:
            if self.__last_page__ == 0:
                self.__scrape_curr_page__()
            else:
                # jump to the next page after the last page we read last time
                if self.__verbose__:
                    self.__getelems__()
                    print(f"\033[1;33mLast Page = \033[1:34m{self.__last_page__}\033[35m Current page = {self.__curr_page__}\033[36m Total pages = {self.__tot_page_count__}\033[94m\n\nAttempting to jump to page {self.__last_page__+1}\033[0m")
                    self.logger.info(f"\033[1;33mLast Page = \033[1:34m{self.__last_page__}\033[35m Current page = {self.__curr_page__}\033[36m Total pages = {self.__tot_page_count__}\033[94m\n\nAttempting to jump to page {self.__last_page__+1}\033[0m")

                self.__jump_to_page__(self.__last_page__)

                # after jumping there, scrape that page
                # after scraping, advance to the next page and read
                # all while curr != last
                while (self.__curr_page__ < self.__tot_page_count__):
                    self.__scrape_curr_page__()
                    self.__goto_next_page__()
                    
        except KeyboardInterrupt:
            print(f'\033[1;31m Scraping interrupted. Gracefully shutting down.\033[0m')
            self.logger.info(f'\033[1;31m Scraping interrupted. Gracefully shutting down.\033[0m')

            if len(self.page_rows):
                print(f"\033[1;36m<Flushing scraped from memory to disk...>\033[0m")
                self.logger.info(f"\033[1;36m<Flushing scraped from memory to disk...>\033[0m")

                with open(self.__fln__, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    while(len(self.page_rows)):
                        row = self.page_rows.popleft()
                        if row[7] not in self.__hashes__:
                            writer.writerow(row)
                            self.__hashes__.add(row[7])
                        else:
                            continue
            self.close()
