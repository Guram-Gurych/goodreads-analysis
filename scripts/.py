import csv
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Union

import yaml
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


load_dotenv()

CONFIG_ENV_NAME: str = os.environ.get("CONFIG_NAME", "goodreads")
CONFIG_PATH: Path = Path(os.environ.get("CONFIG_PATH", "config.yaml"))


def read_config(name: str, path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)[name]


CONFIG: dict = read_config(CONFIG_ENV_NAME, CONFIG_PATH)

BOOKS_URL: str = CONFIG["urls"]["books"]
BOOK_DETAILS_URL: str = CONFIG["urls"]["book_details"]
BOOK_PAGE_SELECTOR: str = CONFIG["selectors"]["book_title"]
GENRE_SELECTOR: str = CONFIG["selectors"]["genre"]
AUTHOR_SELECTOR: str = CONFIG["selectors"]["author"]
RATING_SELECTOR: str = CONFIG["selectors"]["rating"]
RATING_META_SELECTOR: str = CONFIG["selectors"]["rating_meta"]
SHOW_MORE_XPATH: str = CONFIG["selectors"]["show_more"]
TAG_P: str = CONFIG["selectors"]["tag_p"]
BOOK_LINK_SELECTOR: str = CONFIG["selectors"]["book_link"]
USER_AGENT: str = CONFIG["headers"]["user_agent"]
CSV_FIELDNAMES: list[str] = CONFIG["output"]["fieldnames"]
OUTPUT_CSV_PATH: str = CONFIG["output"]["csv_path"]

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:  %(name)s, %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("goodreads-scraper")


def init_driver(headless: bool = True) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={USER_AGENT}")
    return webdriver.Chrome(options=options)


def safe_get_text(
    driver: webdriver.Chrome,
    by: By,
    selector: str,
    attr: str = "text",
    multiple: bool = False,
) -> Union[Optional[str], list[str]]:

    if multiple:
        elements = driver.find_elements(by, selector)
    else:
        elements = [driver.find_element(by, selector)]

    if attr == "text":
        if multiple:
            return [el.text.strip() for el in elements if el.text.strip()]
        else:
            return elements[0].text.strip()

    if multiple:
        return [el.get_attribute(attr) for el in elements if el.get_attribute(attr)]
    return elements[0].get_attribute(attr)


def wait_scroll_and_expand(driver: webdriver.Chrome) -> None:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, BOOK_PAGE_SELECTOR))
    )
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    WebDriverWait(driver, 5).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    try:
        more_button = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, SHOW_MORE_XPATH))
        )
        driver.execute_script("arguments[0].click();", more_button)

    except Exception as error:
        logger.warning(f"Не удалось развернуть список жанров: {str(error)}")


def get_goodreads_book_data(driver: webdriver.Chrome, url: str) -> dict:
    try:
        driver.get(url)
        wait_scroll_and_expand(driver)

        genres = safe_get_text(driver, By.CSS_SELECTOR, GENRE_SELECTOR, multiple=True)
        title = safe_get_text(driver, By.CSS_SELECTOR, BOOK_PAGE_SELECTOR)
        authors = safe_get_text(driver, By.CSS_SELECTOR, AUTHOR_SELECTOR, multiple=True)
        author = ", ".join(authors)
        rating = float(safe_get_text(driver, By.CSS_SELECTOR, RATING_SELECTOR))
        rating_text = safe_get_text(driver, By.CSS_SELECTOR, RATING_META_SELECTOR)
        ratings_count = int(rating_text.split("ratings")[0].strip().replace(",", ""))

        pages = None
        p_tags = driver.find_elements(By.TAG_NAME, TAG_P)
        for p in p_tags:
            text = p.text.strip().lower()
            if "pages" in text:
                pages = int(text.split()[0])
                break

        return {
            "title": title,
            "author": author,
            "rating": rating,
            "genres": genres,
            "pages": pages,
            "ratings_count": ratings_count,
        }

    except TimeoutException as error:
        logger.warning(f"Timeout при загрузке {url}: {error}")
        return {}

    except Exception as error:
        logger.warning(f"Ошибка при обработке {url}: {error}")
        return {}


def get_top_goodreads_book_ids(
    driver: webdriver.Chrome, max_books: int = 100
) -> list[int]:
    book_ids: list[int] = []
    page: int = 1

    while len(book_ids) < max_books:
        driver.get(f"{BOOKS_URL}?page={page}")
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        links = driver.find_elements(By.CSS_SELECTOR, BOOK_LINK_SELECTOR)

        for link in links:
            href = link.get_attribute("href")
            if "/book/show/" in href:
                book_id_part = href.split("/book/show/")[1].split(".")[0]
                if book_id_part.isdigit() and int(book_id_part) not in book_ids:
                    book_ids.append(int(book_id_part))
                    if len(book_ids) >= max_books:
                        break

        logger.info(f"Страница {page} обработана, всего ID: {len(book_ids)}")
        page += 1

    return book_ids


def main() -> None:
    output_path: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", OUTPUT_CSV_PATH)
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logger.info(f"CSV-файл будет сохранён в: {output_path}")

    with open(output_path, mode="w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

        driver = init_driver(headless=True)
        ids = get_top_goodreads_book_ids(driver, 150)
        logger.info(f"Получено {len(ids)} книг")

        for i, book_id in enumerate(ids, 1):
            url = BOOK_DETAILS_URL.format(book_id=book_id)
            logger.info(f"[{i}/{len(ids)}] Обрабатываем: {url}")

            info = get_goodreads_book_data(driver, url)
            if isinstance(info.get("genres"), list):
                info["genres"] = ", ".join(info["genres"])

            writer.writerow(info)
            file.flush()
            logger.info(f"Книга '{info.get('title')}' добавлена в CSV")

        driver.quit()


if __name__ == "__main__":
    main()
