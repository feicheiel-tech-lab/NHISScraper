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

from collections import deque
import re
import os
import pandas as pd

class NHISScraper: 
    def __init__(self, fln = "nhis_payments.csv", verbose=True, t_wait = 17):
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

        # WEBDRIVER & WEBELEMENTS
        self.__driver__ = webdriver.Safari()
        self.__driver__.set_page_load_timeout(700)
        while True:
            try:
                self.__driver__.get("https://www.nhis.gov.gh/payments")
                if self.__verbose__:
                    print("\033[1;32mPage Loaded Successfully\033[0m")
                break
            except Exception as e:
                t_wait = 5
                print(f"\033[31mRetrying in {t_wait} seconds due to error: {e} \033[0m")
                time.sleep(t_wait)

        self.__t_wait__ = t_wait
        self.__nxtbtn__ = 0
        self.__page_ctr__ = 0
        self.__curr_page__ = 0
        self.__tot_page_count__ = 0
        
        # Scrape First page
        try:
            self.scrape()
        except KeyboardInterrupt:
            print(f'\033[1;31m Scraping interrupted. Gracefully shutting down.\033[0m')
            if len(self.page_rows):
                print(f"\033[1;36m<Flushing scraped from memory to disk...>\033[0m")
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
        try:
            __el_ctr__ = len(self.__driver__.find_elements(By.XPATH, "//*"))
        except Exception as e:
            if self.__verbose__:
                print(f'\033[1;31mFailed to count elements')
            return
        
        for i in range(1, __el_ctr__+1):
            try:
                wait = WebDriverWait(self.__driver__, self.__t_wait__)
                el = wait.until(EC.presence_of_element_located((By.XPATH, f'(//*)[{i}]')))
                _el_tag_name_ = el.tag_name or ''; _el_id_ = el.get_attribute('id') or ''; _el_class_ = el.get_attribute('class') or ''
                
                if _el_class_ and _el_tag_name_ and ("button" in _el_tag_name_.lower()) and ("ext" in _el_class_.lower()):
                    self.__nxtbtn__ = i
                    if self.__verbose__:
                        print(f'\033[33mNext Button: {i} --> {el}\033[0m')
                
                if _el_class_ and 'rgCurrentPage' in _el_class_:
                    try:
                        self.__page_ctr__ = int(el.text.strip())
                        if self.__verbose__:
                            print(f'\033[1;36mCurrent Page: {self.__page_ctr__}\033[0m')
                    except ValueError:
                        if self.__verbose__:
                            print(f"<\033[1;31mValueError Received for attempting to cast from {el.text} to int>\033[0m")
                        continue
                
                if _el_tag_name_ and 'strong' in _el_tag_name_.lower():
                    try:
                        self.__tot_page_count__ = int(el.text.strip())
                    except ValueError:
                        if self.__verbose__:
                            print(f'<\033[1;31mValueError Received for attempting to cast from {el.text} to int>\033[0m')
                        continue
            except Exception as e: 
                if self.__verbose__:
                    print(f'\033[1;31mSkipping ahead: {e}\033[0m')
                continue
    
    def __goto_next_page__(self):
        if self.__nxtbtn__ == 0:
            self.__getelems__()
        
        try:
            wait = WebDriverWait(self.__driver__, self.__t_wait__)
            __nxt__ = wait.until(EC.presence_of_element_located((By.XPATH, f'(//*)[{self.__nxtbtn__}]')))

            self.__driver__.execute_script("arguments[0].scrollIntoView({block: 'center'});", __nxt__)
            self.__driver__.execute_script("arguments[0].click();", __nxt__)
        except TimeoutException:
            if self.__verbose__:
                print("\033[1;31mTimeout: Next button not found on page.\033[0m")
            return False
        except Exception as e:
            if self.__verbose__:
                print(f"\033[1;31mClick failed: {e}\033[0m")
            return False
        self.__curr_page__ = self.__page_ctr__
        return True

    def __jump_to_page__(self, _page_num_):
        while (self.__curr_page__ != _page_num_):
            self.__getelems__()
            self.__goto_next_page__()

    def __scrape_curr_page__(self):
        self.__getelems__()
        success = False
        while not success:
            success = self.__do_scrape__()
        self.__curr_page__ = self.__page_ctr__
    
    def __do_scrape__(self, t = 2):
        soup = BeautifulSoup(self.__driver__.page_source, 'html.parser')
        table = soup.find('table')

        if not table and self.__verbose__:
            print(f"No table found on page: {self.__page_ctr__}")
            return False

        rows = table.find_all('tr')[1:]
        self.page_rows = deque()

        for tr in rows:
            row = [td.get_text(strip=True) for td in tr.find_all('td')]
            if len(row) == 5 and row[0] != '':
                row[-2] = self.getClaimsMonth(row[-2])
                row.insert(1, self.getFacilityCategory(row[0]))
                row.append(self.__page_ctr__)
                # append the hash value
                row.append(f"{str(row[0]).split(' ')[0]}{int(float(row[3])*100)}{''.join(str(row[4]).split('/'))}")
                self.page_rows.append(row)
        
        if not self.page_rows and self.__verbose__:
            print("⚠️ row appears empty or malformed.")

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
            print(f'✅ Successfully scraped page {self.__page_ctr__}')
        return True
    
    def scrape(self):
        if self.__last_page__ == 0:
            self.__scrape_curr_page__()
        else:
            # jump to the next page after the last page we read last time
            if self.__verbose__:
                print(f"\033[1;33mLast Page = \033[1:34m{self.__last_page__}\033[35m Current page = {self.__curr_page__}\033[36m Total pages = {self.__tot_page_count__}\033[32m\nAttempting to jump to page {self.__last_page__+1}\033[0m")
            
            self.__jump_to_page__(self.__last_page__)
            
            # after jumping there, scrape that page
            # after scraping, advance to the next page and read
            # all while curr != last
            while (self.__curr_page__ < self.__tot_page_count__):
                self.__scrape_curr_page__()
                self.__goto_next_page__()
                if self.__verbose__:
                    print(f"\033[1;37mSuccessfully added Page \033[31m{self.__curr_page__}")
