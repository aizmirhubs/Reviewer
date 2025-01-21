# Import necessary libraries
import streamlit as st
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
import random
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class StandardizedReview:
    customer_name: str
    stay_date: str
    review_text: str
    rating: float
    source: str


# Initialize Streamlit app
st.title("Otel Yorumu Toplayıcı")
st.markdown("Yorumlarını toplamak istediğiniz otelin Google Maps ve Booking.com URL’lerini girerek müşteri yorumlarını kazıyın.")

# Input fields for URLs
google_url = st.text_input("Google Maps URL’si", placeholder="Google Maps URL’si girin")
booking_url = st.text_input("Booking.com URL’si", placeholder="Booking.com URL’si girin")
webhook_url = st.text_input("Webhook URL’si", placeholder="Kazınan verileri göndermek için webhook URL’si girin")

# Booking.com için sayfa sayısı input'u
search_depth = st.number_input(
    "Arama Derinliği (1-100 arası) (Büyük değer = daha fazla yorum & daha uzun süre)",
    min_value=1,
    max_value=100,
    value=10,
    help="Bu değer, Google Maps'de yorum sayfasının ne kadar aşağı kaydırılacağını, Booking.com'da ise kaç sayfa ilerleneceğini belirler",
)


def initialize_driver():
    try:
        # st.info("WebDriver başlatılıyor...")
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()), options=options
        )
        st.info("Chrome WebDriver başlatıldı.")
        return driver
    except Exception as e:
        st.error(f"WebDriver başlatılırken hata oluştu: {e}")
        return None


def standardize_rating(rating_text):
    try:
        cleaned = "".join(c for c in rating_text if c.isdigit() or c in ".,")
        if " " in cleaned:
            cleaned = cleaned.split()[0]
        cleaned = cleaned.replace(",", ".")
        rating = float(cleaned)
        if rating > 10:
            rating = 10.0
        return round(rating, 1)
    except:
        return 0.0


def standardize_rating(rating_text):
    try:
        if isinstance(rating_text, (int, float)):
            return float(rating_text)

        # Convert to string if not already
        rating_text = str(rating_text).strip()

        # Handle "Puanı X,X" format from Booking
        if "Puanı" in rating_text:
            # Extract last number from string
            numbers = re.findall(r"\d+[,.]?\d*", rating_text)
            if numbers:
                rating_text = numbers[-1]  # Take last number found

        # Handle "X/5" format from Google
        if "/" in rating_text:
            numerator = rating_text.split("/")[0]
            numerator = float(numerator.replace(",", "."))
            denominator = float(rating_text.split("/")[1])
            return round((numerator / denominator) * 10, 1)

        # Clean and convert the rating
        cleaned = "".join(c for c in rating_text if c.isdigit() or c in ".,")
        cleaned = cleaned.replace(",", ".")

        # Handle multiple numbers (take the first valid one)
        if " " in cleaned:
            cleaned = cleaned.split()[0]

        rating = float(cleaned)

        # Scale conversion
        if rating <= 5:
            rating = rating * 2
        elif rating > 10:
            rating = 10.0

        return round(rating, 1)

    except Exception as e:
        st.warning(f"Yorum skoru dönüştürülürken bir hata oluştu: {rating_text} - {str(e)}")
        return 0.0


def scrape_google_maps(url, driver, search_depth=20):
    try:
        driver.get(url)

        try:
            wait = WebDriverWait(driver, 10)
            see_all_button = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "button.HHrUdb.fontTitleSmall.rqjGif")
                )
            )

            if not see_all_button:
                see_all_button = wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//button[contains(@class, 'HHrUdb')]//span[contains(text(), 'yorum')]/..",
                        )
                    )
                )

            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", see_all_button
            )
            time.sleep(1)

            try:
                see_all_button.click()
            except:
                driver.execute_script("arguments[0].click();", see_all_button)

            time.sleep(2)

        except Exception as e:
            st.warning(f"Yorum düğmesi bulunamadı veya tıklanamadı: {str(e)}")

        scrollable_div = None
        try:
            scrollable_div = driver.find_element(
                By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde"
            )
        except:
            st.warning("Google Maps: Kaydırılabilir yorum kutusu bulunamadı. Pencere kaydırması kullanılacak...")

        progress_bar = st.progress(0)
        for i in range(search_depth * 5):
            progress_bar.progress(int(((i + 1) / (search_depth * 5)) * 100))
            if scrollable_div:
                driver.execute_script("arguments[0].scrollBy(0, 3000);", scrollable_div)
            else:
                driver.execute_script("window.scrollBy(0, 3000);")
            time.sleep(random.uniform(1.0, 2.5))

            review_elements = driver.find_elements(By.CLASS_NAME, "jJc9Ad")

        reviews = []
        for idx, element in enumerate(review_elements):
            try:
                customer_name = element.find_element(
                    By.CLASS_NAME, "d4r55"
                ).text.strip()
                try:
                    review_text = element.find_element(By.CLASS_NAME, "wiI7pd").text.strip()
                except:
                    review_text = ""
                date = element.find_element(By.CLASS_NAME, "xRkPPb").text.strip()
                cleaned_date = date.replace("Google\n, ", "").strip()
                stars = element.find_elements(By.CLASS_NAME, "elGi1d")
                rating_element = element.find_element(By.CLASS_NAME, "fzvQIb")
                rating_text = rating_element.text if rating_element else "0/5"

                standardized_review = StandardizedReview(
                    customer_name=customer_name or "-",
                    stay_date=cleaned_date or "-",
                    review_text=review_text or "-",
                    rating=standardize_rating(rating_text),
                    source="Google Maps",
                )
                reviews.append(standardized_review.__dict__)
            except Exception as e:
                st.error(f"Google Maps: Yorum işlerken bir hata oluştu {idx + 1}: {e}")
                continue
        return reviews
    except Exception as e:
        st.error(f"Google Maps yorumları alınırken bir hata oluştu: {e}")
        return []


def scrape_booking(url, driver, search_depth=5):
    try:
        st.info("Booking.com yorumları kazınıyor...")
        driver.get(url)
        time.sleep(3)

        def click_with_retry(selector, max_attempts=3):
            for attempt in range(max_attempts):
                try:
                    button = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                    time.sleep(2)
                    button.click()
                    return True
                except StaleElementReferenceException:
                    time.sleep(2)
                    continue
                except Exception as e:
                    st.error(f"Error clicking button (attempt {attempt + 1}): {str(e)}")
            return False

        if click_with_retry("button[data-testid='fr-read-all-reviews']"):
            time.sleep(3)
        else:
            st.error("Tüm yorumları göster düğmesine tıklanamadı.")
            return []

        def scroll_reviews(driver, num_attempts):
            try:
                reviews_container = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "dd5dccd82f"))
                )
                last_height = 0
                for i in range(num_attempts):

                    driver.execute_script(
                        """
                        arguments[0].scrollTo({
                            top: arguments[0].scrollHeight,
                            behavior: 'smooth'
                        });
                        """,
                        reviews_container,
                    )

                    time.sleep(2)

                    new_height = driver.execute_script(
                        "return arguments[0].scrollHeight", reviews_container
                    )
                    if new_height == last_height:
                        break
                    last_height = new_height

            except Exception as e:
                st.error(f"Booking yorumları alınırken bir hata oluştu: {e}")
                return False

        scroll_reviews(driver, 2)

        all_reviews = []
        review_elements = driver.find_elements(By.CSS_SELECTOR, "div.d799cd346c[data-testid='review-card']")

        def extract_review_data(review):
            try:
                # Extract customer name
                try:
                    name = review.find_element(By.CLASS_NAME, "a3332d346a").text.strip()
                except:
                    name = "-"

                # Extract stay date
                try:
                    stay_date = review.find_element(By.CSS_SELECTOR, "[data-testid='review-stay-date']").text.strip()
                except:
                    stay_date = "-"

                # Extract positive review text
                try:
                    positive_element = review.find_element(By.CLASS_NAME, "a53cbfa6de.b5726afd0b")
                    positive_text = positive_element.text.strip() if positive_element else "/"
                except:
                    positive_text = "/"

                # Extract negative review text
                try:
                    negative_element = review.find_element(By.CLASS_NAME, "a53cbfa6de.b5726afd0b")
                    negative_text = negative_element.text.strip() if negative_element else "/"
                except:
                    negative_text = "/"

                # Extract review rating
                try:
                    score_element = review.find_element(By.CSS_SELECTOR, "[data-testid='review-score'] div")
                    score_text = score_element.text.strip() if score_element else "0"
                except:
                    score_text = "0"

                return StandardizedReview(
                    customer_name=name or "-",
                    stay_date=stay_date or "-",
                    review_text=f"Positive: {positive_text}\nNegative: {negative_text}",
                    rating=standardize_rating(score_text),
                    source="Booking.com"
                )

            except Exception as e:
                st.error(f"Yorum verisi toplanırken bir hata oluştu: {str(e)}")
                return None

        for idx, review in enumerate(review_elements):
            all_reviews.append(extract_review_data(review).__dict__)

        def paginate_reviews(driver, search_depth):
            try:
                all_reviews = []
                progress_bar = st.progress(0)
                for page in range(1, search_depth + 1):
                    progress_bar.progress(int((page / search_depth) * 100))

                    pagination_section = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "ef2dbaeb17"))
                    )
                    next_buttons = pagination_section.find_elements(By.CLASS_NAME, "a83ed08757")

                    next_page_clicked = False

                    for button in next_buttons:
                        if not button.get_attribute("aria-current"):
                            driver.execute_script("arguments[0].scrollIntoView(true);", button)
                            time.sleep(2)
                            button.click()
                            next_page_clicked = True
                            break

                    if not next_page_clicked:
                        st.warning(f"Next page button not found. Ending pagination at page {page}")
                        break

                    time.sleep(3)

                    review_elements = driver.find_elements(By.CSS_SELECTOR, "div.d799cd346c[data-testid='review-card']")

                    for idx, review in enumerate(review_elements):
                        extracted_review = extract_review_data(review)
                        if extracted_review:
                            all_reviews.append(extracted_review.__dict__)

                return all_reviews

            except Exception as e:
                st.error(f"Error during pagination: {e}")
                return []

        all_reviews = paginate_reviews(driver, search_depth)

        return all_reviews

    except Exception as e:
        st.error(f"Error scraping Booking.com: {e}")
        return []


# Single button with unique key
if st.button("Başlat", key="scrape_button"):
    st.info("Kazıma işlemi yapılıyor... Lütfen bekleyin.")
    all_reviews = []

    driver = initialize_driver()
    if driver:
        if google_url:
            st.info("Google Maps yorumları kazınıyor...")
            google_reviews = scrape_google_maps(google_url, driver, search_depth)
            st.success(f"Google Maps üzerinden {len(google_reviews)} yorum kazındı.")
            all_reviews.extend(google_reviews)
        if booking_url:
            st.info("Booking.com yorumları kazınıyor...")
            booking_reviews = scrape_booking(booking_url, driver, search_depth)
            st.success(f"Booking.com üzerinden {len(booking_reviews)} yorum kazındı.")
            all_reviews.extend(booking_reviews)

        driver.quit()

        if all_reviews:
            with open("müşteri_yorumları.json", "w", encoding="utf-8") as file:
                json.dump(all_reviews, file, ensure_ascii=False, indent=4)
            st.success("Kazıma işlemi başarıyla tamamlandı. Veriler müşteri_yorumları.json dosyasına kaydedildi.")
            if webhook_url:
                try:
                    response = requests.post(webhook_url, json=all_reviews)
                    if response.status_code == 200:
                        st.success("Veriler webhook'a başarıyla gönderildi.")
                    else:
                        st.error(f"Webhook error: {response.status_code} - {response.text}")
                except Exception as e:
                    st.error(f"Webhook'a veri gönderilirken hata oluştu: {e}")
            else:
                st.warning("Webhook URL’si sağlanmadı. Veri gönderilmedi.")
        else:
            st.warning("Kazınan yorum yok. Lütfen sağlanan URL’leri kontrol edin.")
