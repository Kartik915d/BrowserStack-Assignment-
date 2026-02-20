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
                title = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                ).text
                log(session_name, f"Title (ES): {title}")
                titles_spanish.append(title)
            except TimeoutException:
                log(session_name, "Title not found")
                titles_spanish.append("Unknown")

            # CONTENT (first 3 paragraphs)
            try:
                paragraphs = driver.find_elements(By.CSS_SELECTOR, "article p")
                full_text = ""

                for p in paragraphs[:3]:
                    if p.text.strip():
                        full_text += p.text.strip() + " "

                if full_text:
                    wrapped = textwrap.fill(full_text.strip(), width=80)
                    log(session_name, f"Content:\n{wrapped}")
                else:
                    log(session_name, "Content not found")

            except Exception:
                log(session_name, "Content not found")

            # IMAGE
            try:
                image = driver.find_element(By.CSS_SELECTOR, "article img")
                image_url = image.get_attribute("src")

                if image_url:
                    file_name = f"{session_name}_{i}.jpg"
                    file_path = os.path.join(IMAGE_FOLDER, file_name)
                    download_image(image_url, file_path, session_name)

            except Exception:
                log(session_name, "Image not found")

        # ==========================================
        # TRANSLATION
        # ==========================================

        log(session_name, "\nTranslated Titles:")

        translator = GoogleTranslator(source="es", target="en")
        titles_english = translator.translate_batch(titles_spanish)

        for idx, t in enumerate(titles_english, 1):
            log(session_name, f"{idx} - {t}")

        # ==========================================
        # WORD FREQUENCY
        # ==========================================

        log(session_name, "\nWord Frequency (Repeated more than 2 times):")

        stopwords = {"the", "and", "for", "with", "that", "this", "will", "are", "but", "not"}

        words = []
        for title in titles_english:
            clean_words = re.findall(r"\b[a-zA-Z]+\b", title.lower())
            for word in clean_words:
                if len(word) > 2 and word not in stopwords:
                    words.append(word)

        count = Counter(words)

        repeated = False
        for word, freq in count.items():
            if freq > 2:
                log(session_name, f"{word} -> {freq}")
                repeated = True

        if not repeated:
            log(session_name, "No word repeated more than twice")

        log(session_name, "Session Finished")

    finally:
        driver.quit()


# ==========================================
# BROWSERSTACK ENVIRONMENTS (5 PARALLEL)
# ==========================================

def get_environments():
    return [
        {
            "browserName": "Chrome",
            "browserVersion": "latest",
            "bstack:options": {
                "os": "Windows",
                "osVersion": "11",
                "sessionName": "Windows Chrome"
            }
        },
        {
            "browserName": "Firefox",
            "browserVersion": "latest",
            "bstack:options": {
                "os": "OS X",
                "osVersion": "Ventura",
                "sessionName": "Mac Firefox"
            }
        },
        {
            "browserName": "Edge",
            "browserVersion": "latest",
            "bstack:options": {
                "os": "Windows",
                "osVersion": "10",
                "sessionName": "Windows Edge"
            }
        },
        {
            "browserName": "Chrome",
            "browserVersion": "latest",
            "bstack:options": {
                "os": "OS X",
                "osVersion": "Monterey",
                "sessionName": "Mac Chrome"
            }
        },
        {
            "browserName": "Safari",
            "browserVersion": "latest",
            "bstack:options": {
                "os": "OS X",
                "osVersion": "Ventura",
                "sessionName": "Mac Safari"
            }
        }
    ]


# ==========================================
# BROWSERSTACK EXECUTION
# ==========================================

def run_browserstack_test(caps, username, access_key):
    try:
        print("Launching:", caps["bstack:options"]["sessionName"])

        options = webdriver.ChromeOptions()

        for key, value in caps.items():
            options.set_capability(key, value)

        # W3C AUTHENTICATION (Correct Method)
        hub_url = f"https://{username}:{access_key}@hub-cloud.browserstack.com/wd/hub"

        driver = webdriver.Remote(
            command_executor=hub_url,
            options=options
        )

        scrape_articles(driver, caps["bstack:options"]["sessionName"])

    except Exception as e:
        print("BROWSERSTACK ERROR:", e)


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    print("\nEnter BrowserStack credentials (or press Enter to skip cloud test)\n")

    username = input("Username: ").strip()
    access_key = input("Access Key: ").strip()

    # Local run
    print("\nStarting Local Test...\n")
    local_driver = webdriver.Chrome()
    scrape_articles(local_driver, "Local")

    # BrowserStack run
    if username and access_key:
        print("\nStarting BrowserStack Tests...\n")

        environments = get_environments()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for env in environments:
                futures.append(
                    executor.submit(run_browserstack_test, env, username, access_key)
                )

            # Force exception visibility
            for future in futures:
                future.result()

    else:
        print("\nBrowserStack test skipped.")