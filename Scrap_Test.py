import os
import re
import requests
import textwrap
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

URL = "https://elpais.com/opinion/"
IMAGE_FOLDER = "article_images"

# ==========================================
# LOGGER
# ==========================================

def log(session, message):
    print(f"[{session}] {message}")

# ==========================================
# BROWSERSTACK STATUS UPDATER
# ==========================================

def update_bstack_status(driver, status, reason):
    """Sends a JavaScript executor command to update the BrowserStack dashboard."""
    try:
        # Sanitize reason for JS string
        clean_reason = reason.replace('"', "'").replace("\n", " ")[:255]
        executor_object = {
            "action": "setSessionStatus",
            "arguments": {"status": status, "reason": clean_reason}
        }
        driver.execute_script(f'browserstack_executor: {json.dumps(executor_object)}')
    except:
        # Ignore if running locally or if driver is closed
        pass

# ==========================================
# IMAGE DOWNLOAD
# ==========================================

def download_image(image_url, file_path, session):
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(response.content)
        log(session, f"Image saved: {file_path}")
    except Exception as e:
        log(session, f"Image download failed: {e}")

# ==========================================
# SCRAPER FUNCTION
# ==========================================

def scrape_articles(driver, session_name="Local"):
    log(session_name, "Starting session")

    try:
        driver.get(URL)

        # Accept cookies
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "didomi-notice-agree-button"))
            )
            cookie_btn.click()
            log(session_name, "Cookies accepted")
        except TimeoutException:
            pass

        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article header h2 a"))
        )

        articles = driver.find_elements(By.CSS_SELECTOR, "article header h2 a")[:5]
        links = [a.get_attribute("href") for a in articles]

        os.makedirs(IMAGE_FOLDER, exist_ok=True)
        titles_spanish = []

        for i, link in enumerate(links, 1):
            driver.get(link)
            log(session_name, f"\nArticle {i}")

            # TITLE
            try:
                title_el = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                title = title_el.text
                log(session_name, f"Title (ES): {title}")
                titles_spanish.append(title)
            except TimeoutException:
                log(session_name, "Title not found")
                titles_spanish.append("Unknown")

            # CONTENT
            try:
                paragraphs = driver.find_elements(By.CSS_SELECTOR, "article p")
                full_text = " ".join([p.text.strip() for p in paragraphs[:3] if p.text.strip()])
                if full_text:
                    wrapped = textwrap.fill(full_text, width=80)
                    log(session_name, f"Content:\n{wrapped}")
            except Exception:
                log(session_name, "Content not found")

            # IMAGE
            try:
                image = driver.find_element(By.CSS_SELECTOR, "article img")
                image_url = image.get_attribute("src")
                if image_url:
                    file_path = os.path.join(IMAGE_FOLDER, f"{session_name}_{i}.jpg")
                    download_image(image_url, file_path, session_name)
            except Exception:
                log(session_name, "Image not found")

        # TRANSLATION & ANALYSIS
        log(session_name, "\nTranslating...")
        translator = GoogleTranslator(source="es", target="en")
        titles_english = translator.translate_batch(titles_spanish)

        for idx, t in enumerate(titles_english, 1):
            log(session_name, f"{idx} - {t}")

        # Check word frequency
        words = []
        for title in titles_english:
            clean_words = re.findall(r"\b[a-zA-Z]+\b", title.lower())
            words.extend([w for w in clean_words if len(w) > 2])
        
        count = Counter(words)
        for word, freq in count.items():
            if freq > 2:
                log(session_name, f"Repeated: {word} -> {freq}")

        log(session_name, "Session Finished")
        return True # Success

    except Exception as e:
        log(session_name, f"Error during scraping: {e}")
        raise e

# ==========================================
# BROWSERSTACK ENVIRONMENTS
# ==========================================

def get_environments():
    # Adding project/build grouping for organized dashboard
    common_options = {
        "projectName": "El Pais Scraping",
        "buildName": "BStack Build 1.0",
    }
    
    envs = [
        {"browserName": "Chrome", "browserVersion": "latest", "bstack:options": {"os": "Windows", "osVersion": "11", "sessionName": "Windows Chrome"}},
        {"browserName": "Firefox", "browserVersion": "latest", "bstack:options": {"os": "OS X", "osVersion": "Ventura", "sessionName": "Mac Firefox"}},
        {"browserName": "Edge", "browserVersion": "latest", "bstack:options": {"os": "Windows", "osVersion": "10", "sessionName": "Windows Edge"}},
        {"browserName": "Chrome", "browserVersion": "latest", "bstack:options": {"os": "OS X", "osVersion": "Monterey", "sessionName": "Mac Chrome"}},
        {"browserName": "Safari", "browserVersion": "latest", "bstack:options": {"os": "OS X", "osVersion": "Ventura", "sessionName": "Mac Safari"}}
    ]
    
    for env in envs:
        env["bstack:options"].update(common_options)
    return envs

# ==========================================
# BROWSERSTACK EXECUTION
# ==========================================

import json

def run_browserstack_test(caps, username, access_key):
    driver = None
    session_name = caps["bstack:options"]["sessionName"]
    try:
        log(session_name, f"Launching on BrowserStack...")
        options = webdriver.ChromeOptions()
        for key, value in caps.items():
            options.set_capability(key, value)

        hub_url = f"https://{username}:{access_key}@hub-cloud.browserstack.com/wd/hub"
        driver = webdriver.Remote(command_executor=hub_url, options=options)

        scrape_articles(driver, session_name)
        
        # Mark PASSED on BrowserStack
        update_bstack_status(driver, "passed", "Scraping completed without errors.")

    except Exception as e:
        log(session_name, f"BROWSERSTACK FAIL: {e}")
        if driver:
            update_bstack_status(driver, "failed", str(e))
    finally:
        if driver:
            driver.quit()

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    import sys

    username = input("BrowserStack Username: ").strip()
    access_key = input("BrowserStack Access Key: ").strip()

    # 1. LOCAL TEST
    print("\n--- Starting Local Test ---")
    try:
        local_driver = webdriver.Chrome()
        scrape_articles(local_driver, "Local")
    except Exception as e:
        print(f"Local run failed: {e}")
    finally:
        try: local_driver.quit()
        except: pass

    # 2. CLOUD TEST
    if username and access_key:
        print(f"\n--- Starting 5 Parallel BrowserStack Tests ---")
        environments = get_environments()
        with ThreadPoolExecutor(max_workers=5) as executor:
            for env in environments:
                executor.submit(run_browserstack_test, env, username, access_key)
    else:
        print("\nCloud credentials missing. Skipping BrowserStack.")