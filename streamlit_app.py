#!/usr/bin/env python3
"""
Streamlit app: given a web address, fetch the page, extract basic metadata,
build an APA-style web reference, and output a RIS record for EndNote.

Heuristics:
- Title from citation_title, og:title, twitter:title, or <title>.
- Author from meta[name="author"], meta[property="article:author"],
  meta[name="citation_author"], etc.
- Date from article:published_time, citation_publication_date, dc.date, etc.
- Site name from og:site_name or domain.
"""

import re
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional

import requests
import streamlit as st
from bs4 import BeautifulSoup


def fetch_html(url: str) -> Optional[str]:
    """Fetch HTML content from a URL. Returns text or None on failure."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; APA-RIS-Bot/1.0)"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        st.error(f"Error fetching URL: {e}")
        return None


def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """Collect relevant meta tag values into a simple dictionary."""
    meta_info: Dict[str, List[str]] = {
        "citation_title": [],
        "og_title": [],
        "twitter_title": [],
        "meta_title": [],
        "author": [],
        "citation_author": [],
        "article_author": [],
        "date": [],
        "publication_date": [],
        "dc_date": [],
        "article_published_time": [],
        "site_name": [],
    }

    # Standard title tag
    if soup.title and soup.title.string:
        meta_info["meta_title"].append(soup.title.string.strip())

    for tag in soup.find_all("meta"):
        name = (tag.get("name") or "").lower()
        prop = (tag.get("property") or "").lower()
        content = tag.get("content") or ""
        content = content.strip()
        if not content:
            continue

        if name == "citation_title":
            meta_info["citation_title"].append(content)
        elif prop == "og:title":
            meta_info["og_title"].append(content)
        elif name == "twitter:title":
            meta_info["twitter_title"].append(content)
        elif name == "author":
            meta_info["author"].append(content)
        elif name == "citation_author":
            meta_info["citation_author"].append(content)
        elif prop == "article:author":
            meta_info["article_author"].append(content)
        elif name in ["date", "article:published_time"]:
            meta_info["date"].append(content)
        elif name == "citation_publication_date":
            meta_info["publication_date"].append(content)
        elif name.startswith("dc.date"):
            meta_info["dc_date"].append(content)
        elif prop == "article:published_time":
            meta_info["article_published_time"].append(content)
        elif prop == "og:site_name":
            meta_info["site_name"].append(content)

    return meta_info


def choose_title(meta: Dict[str, List[str]]) -> Optional[str]:
    """Pick the best available title."""
    for key in ["citation_title", "og_title", "twitter_title", "meta_title"]:
        if meta[key]:
            return meta[key][0]
    return None


def choose_authors(meta: Dict[str, List[str]]) -> Optional[str]:
    """
    Pick an author string.
    Multiple citation_author values are joined with ', '.
    """
    if meta["citation_author"]:
        return ", ".join(meta["citation_author"])
    if meta["author"]:
        return meta["author"][0]
    if meta["article_author"]:
        return meta["article_author"][0]
    return None


def extract_year_from_dates(dates: List[str]) -> Optional[str]:
    """Try to find a four digit year in a list of date strings."""
    for d in dates:
        # Try to parse ISO-like first
        # Fall back to regex
        match = re.search(r"\b(19|20)\d{2}\b", d)
        if match:
            return match.group(0)
    return None


def choose_year(meta: Dict[str, List[str]]) -> Optional[str]:
    """Pick a publication year from the collected meta fields."""
    candidates: List[str] = []
    candidates.extend(meta["article_published_time"])
    candidates.extend(meta["publication_date"])
    candidates.extend(meta["dc_date"])
    candidates.extend(meta["date"])

    year = extract_year_from_dates(candidates)
    return year


def choose_site_name(meta: Dict[str, List[str]], url: str) -> str:
    """Pick a site name from og:site_name or fall back to domain."""
    if meta["site_name"]:
        return meta["site_name"][0]
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    return host or "Website"


def build_apa_reference(
    url: str,
    title: Optional[str],
    authors: Optional[str],
    year: Optional[str],
    site_name: Optional[str],
) -> str:
    """
    Build a simple APA style web reference line.
    This is approximate, but good enough for note and RIS.
    """
    # Author
    author_part = authors if authors else site_name or "Author"

    # Year
    year_part = year if year else "n.d."

    # Title
    title_part = title if title else "Title not available"

    site_part = site_name if site_name else ""

    reference = f"{author_part}. ({year_part}). {title_part}. {site_part}. Retrieved from {url}"
    return reference.strip()


def build_ris_record(
    url: str,
    title: Optional[str],
    authors: Optional[str],
    year: Optional[str],
    apa_ref: str,
) -> str:
    """
    Build a RIS record for an electronic resource.

    TY: ELEC
    AU: authors
    PY: year
    TI: title
    UR: url
    N1: full APA reference
    """
    lines: List[str] = []
    lines.append("TY  - ELEC")

    if authors:
        lines.append(f"AU  - {authors}")

    if title:
        lines.append(f"TI  - {title}")

    if year:
        lines.append(f"PY  - {year}")

    lines.append(f"UR  - {url}")
    lines.append(f"N1  - {apa_ref}")
    lines.append("ER  - ")

    return "\n".join(lines) + "\n\n"


# Streamlit UI

st.title("URL to RIS (Web Page to EndNote)")

st.write(
    "Enter a web address below. The app will fetch the page, look for metadata "
    "to infer author, year, title, and site name, build an APA-style web "
    "reference, and create a RIS record for EndNote."
)

default_url = "https://www.theguardian.com/australia-news"

url_input = st.text_input("Web address (URL)", value=default_url)

if st.button("Fetch and generate RIS"):
    url = url_input.strip()
    if not url:
        st.warning("Please enter a URL.")
    else:
        html = fetch_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            meta = extract_meta_tags(soup)

            title = choose_title(meta)
            authors = choose_authors(meta)
            year = choose_year(meta)
            site_name = choose_site_name(meta, url)

            apa_ref = build_apa_reference(url, title, authors, year, site_name)
            ris_record = build_ris_record(url, title, authors, year, apa_ref)

            st.subheader("Detected metadata")
            st.write(f"Title: {title or 'Not found'}")
            st.write(f"Author(s): {authors or 'Not found'}")
            st.write(f"Year: {year or 'Not found'}")
            st.write(f"Site name: {site_name}")

            st.subheader("APA-style reference (approximate)")
            st.text_area("APA reference", apa_ref, height=120)

            st.subheader("RIS record")
            st.text_area("RIS output", ris_record, height=200)

            st.download_button(
                label="Download RIS file",
                data=ris_record.encode("utf-8"),
                file_name="web_reference.ris",
                mime="application/x-research-info-systems",
            )
