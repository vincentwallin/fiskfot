from __future__ import annotations

import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.blocket.se"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


def clean_number(value: Any) -> int | None:
    """Omvandlar exempelvis '249 000 kr' till 249000."""

    if value is None:
        return None

    text = str(value)

    numbers = re.sub(r"[^\d]", "", text)

    if not numbers:
        return None

    try:
        return int(numbers)
    except ValueError:
        return None


def get_json_ld(soup: BeautifulSoup) -> list[dict]:
    """Hämtar JSON-LD-data från sidan."""

    import json

    results = []

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        try:
            data = json.loads(script.string or script.text)

            if isinstance(data, dict):
                results.append(data)

            elif isinstance(data, list):
                results.extend(
                    item
                    for item in data
                    if isinstance(item, dict)
                )

        except (json.JSONDecodeError, TypeError):
            continue

    return results


def extract_cars(html: str) -> list[dict]:
    """
    Försöker extrahera bilannonser från Blockets HTML.

    OBS:
    Blocket kan ändra sin frontend och sina HTML-strukturer.
    Funktionen är därför medvetet försiktig och bör underhållas
    när webbplatsen ändras.
    """

    soup = BeautifulSoup(html, "html.parser")

    cars = []

    # Försök först med JSON-LD.
    json_ld = get_json_ld(soup)

    for item in json_ld:
        item_type = item.get("@type")

        if item_type not in ("Product", "Vehicle", "Car"):
            continue

        title = (
            item.get("name")
            or item.get("model")
            or "Okänd bil"
        )

        url = item.get("url")

        price = None

        offers = item.get("offers")

        if isinstance(offers, dict):
            price = clean_number(offers.get("price"))

        cars.append(
            {
                "title": title,
                "price": price,
                "year": None,
                "mileage": None,
                "location": None,
                "url": url,
            }
        )

    # Generisk fallback: leta efter länkar som ser ut som annonser.
    if not cars:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(" ", strip=True)

            if not text:
                continue

            if len(text) < 5:
                continue

            # Undvik att samla navigationslänkar.
            if "/item/" not in href and "/annons/" not in href:
                continue

            if href.startswith("/"):
                href = BASE_URL + href

            cars.append(
                {
                    "title": text,
                    "price": None,
                    "year": None,
                    "mileage": None,
                    "location": None,
                    "url": href,
                }
            )

    # Ta bort dubbletter.
    unique = {}

    for car in cars:
        url = car.get("url")

        if url:
            unique[url] = car

    return list(unique.values())


def search_cars(
    query: str,
    min_price: int = 0,
    max_price: int = 500000,
    min_year: int = 1900,
    max_year: int = 2030,
    max_mileage: int = 20000,
    max_results: int = 20,
) -> list[dict]:
    """
    Söker efter bilar.

    Filtrering görs även lokalt eftersom sökparametrarna på
    webbplatsen kan ändras.
    """

    params = {
        "q": query,
    }

    search_url = f"{BASE_URL}/annonser/bilar"

    response = requests.get(
        search_url,
        params=params,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    cars = extract_cars(response.text)

    filtered = []

    for car in cars:
        price = car.get("price")
        year = car.get("year")
        mileage = car.get("mileage")

        if price is not None:
            if price < min_price:
                continue

            if price > max_price:
                continue

        if year is not None:
            if year < min_year or year > max_year:
                continue

        if mileage is not None:
            if mileage > max_mileage:
                continue

        filtered.append(car)

        if len(filtered) >= max_results:
            break

    # Artig fördröjning mellan framtida requests.
    time.sleep(1)

    return filtered
