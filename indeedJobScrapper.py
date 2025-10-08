import time, json, re
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from openai import OpenAI
import os
from datetime import datetime, timedelta

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)

# 💬 LLM Extraction
def extract_job_details(description):
    prompt = f"""
You are an intelligent parser. Given the following job description, extract:

- Required skills (as a list)
- Minimum experience in years (number only)
- Qualifications (as a list)
- Duration (e.g. "6 months", "1 year", or "None" if not specified)
- Start date if mentioned (in yyyy-mm-dd format if possible, otherwise "None")
- Expiration date if mentioned (in yyyy-mm-dd format if possible, otherwise "None")
- Tags: Choose only from ['Software', 'AI/ML', 'Data Science', 'Design', 'Marketing', 'Consulting', 'Business']
- Job Type (Full-time, Internship, Contract, etc.)
- Employment Type (Remote, On-site, Hybrid)

Job Description:
\"\"\"
{description}
\"\"\"

Respond only in this JSON format (no extra text):

{{
  "skills": [],
  "minExperience": 0,
  "qualifications": [],
  "duration": "None",
  "startDate": "None",
  "expiresAt": "None",
  "tags": [],
  "jobType": "Not specified",
  "employmentType": "Not specified"
}}
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts structured data."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print("⚠️ LLM extraction error:", e)
        return {
            "skills": [],
            "minExperience": 0,
            "qualifications": [],
            "duration": "None",
            "startDate": "None",
            "expiresAt": (datetime.today() + timedelta(days=7)).date().isoformat(),
            "tags": [],
            "jobType": "Not specified",
            "employmentType": "Not specified"
        }

# 🛑 CAPTCHA Handler
def handle_captcha(driver):
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            src = frame.get_attribute("src")
            if src and "captcha" in src:
                print("🚨 CAPTCHA detected in iframe.")
                input("🛑 Solve the CAPTCHA, then press ENTER to continue...")
                return True
        divs = driver.find_elements(By.XPATH, '//div[contains(@id, "px-captcha") or contains(@class, "g-recaptcha")]')
        if divs:
            print("🚨 CAPTCHA detected in div.")
            input("🛑 Solve the CAPTCHA, then press ENTER to continue...")
            return True
    except Exception as e:
        print("Error while checking CAPTCHA:", e)
    return False

# 🚀 Driver
def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    return uc.Chrome(options=options)

# 👤 Manual Login
def wait_for_login(driver):
    driver.get("https://www.indeed.com/account/login")
    print("🔐 Log in manually. Solve CAPTCHA if prompted.")
    input("✅ Press ENTER when you're fully logged in...\n")

# 📆 Date Parser
def parse_date(text):
    if not text or str(text).lower() in ["none", "not specified", ""]:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except:
        return None

# 🔍 Main Scraper
def scrape_indeed_jobs(driver, base_url, pages=1):
    all_jobs = []
    wait = WebDriverWait(driver, 15)

    for page in range(pages):
        page_url = base_url.replace("start=0", f"start={page * 10}")
        driver.get(page_url)
        print(f"\n📄 Scraping: {page_url}")
        time.sleep(4)

        if handle_captcha(driver):
            time.sleep(2)

        job_cards = driver.find_elements(By.CLASS_NAME, "job_seen_beacon")
        print(f"➡️ Found {len(job_cards)} jobs")

        for i, job in enumerate(job_cards, 1):
            try:
                title = title = job.find_element(By.XPATH, './/span[starts-with(@id, "jobTitle-")]').text
                company = company = job.find_element(By.XPATH, './/span[@data-testid="company-name"]').text.strip()
                location = job.find_element(By.XPATH, './/div[@data-testid="text-location"]').text
                try:
                    logo = job.find_element(By.TAG_NAME, "img").get_attribute("src")
                except:
                    logo = "Not available"
                try:
                    snippets = job.find_elements(By.XPATH, './/div[@data-testid="attribute_snippet_testid"]')
                    for s in snippets:
                        text = s.text.strip()
                        if "₹" in text or "per month" in text or "per year" in text:
                            salary = text
                            break
                except:
                    salary = "Not specified"

                if handle_captcha(driver):
                    time.sleep(2)

                job.click()
                time.sleep(3)

                if handle_captcha(driver):
                    time.sleep(2)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "jobDescriptionText"))
                    )
                    desc_elem = driver.find_element(By.ID, "jobDescriptionText")
                    # raw_html = desc_elem.get_attribute("innerHTML")
                    # soup = BeautifulSoup(raw_html, "html.parser")
                    # desc = soup.get_text(separator="\n").strip()
                    desc = desc_elem.text.strip()
                except TimeoutException:
                    print("⚠️ Job description panel did not load in time.")
                    desc = "Not available"
                try:
                    apply_buttons = driver.find_elements(
                        By.XPATH,
                        '//button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "apply")]'
                    )

                    external_link = driver.current_url
                    for btn in apply_buttons:
                        href = btn.get_attribute("href")
                        if href and href.startswith("http"):
                            external_link = href
                            break
                except:
                    external_link = page_url
                parsed = extract_job_details(desc)

                all_jobs.append({
                    "sourceType": "company",
                    "CompanyName": company,
                    "CompanyLogo": logo,
                    "jobTitle": title,
                    "jobDescription": desc,
                    "skills": parsed["skills"],
                    "location": location,
                    "employmentType": parsed["employmentType"],
                    "jobType": parsed["jobType"],
                    "minExperience": parsed["minExperience"],
                    "salaryRange": salary,
                    "duration": parsed["duration"],
                    "startDate": parse_date(parsed["startDate"]),
                    "externalLink": external_link,
                    "qualifications": parsed["qualifications"],
                    "tags": parsed["tags"],
                    "expiresAt": parse_date(parsed["expiresAt"]) or (datetime.today() + timedelta(days=7)).date().isoformat()
                })

                print(f"✅ Scraped: {title} @ {company}")

            except Exception as e:
                print(f"❌ Error scraping job: {e}")
                continue

    return pd.DataFrame(all_jobs)

# 🏁 Entry Point
if __name__ == "__main__":
    driver = get_driver()
    wait_for_login(driver)

    # 🎯 Your job search URL
    base_url = "https://in.indeed.com/jobs?q=data+engineer&l=India&sc=0kf%3Aattr%287EQCZ%7CVDTG7%252COR%29%3B&from=searchOnDesktopSerp&start=0vjk%3Daa8d08738f6f213e&vjk=aa8d08738f6f213e"

    df = scrape_indeed_jobs(driver, base_url, pages=2)
    df.to_csv("indeed_jobs_data_engineering.csv", index=False)
    print("\n✅ Jobs saved to indeed_jobs.csv")
