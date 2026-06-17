# Costco-Inspired Sales & Inventory Insights System

A hybrid, production-ready analytics dashboard built with **Streamlit** and powered by a live **PostgreSQL** database. The system features structural rule-based business analytics alongside an unstructured **AI Supply Chain Copilot** powered by **Google Gemini 2.5 Flash**.

---

## Key Features

* **AI Supply Chain Copilot:** Translate natural language business questions directly into optimized PostgreSQL queries in real-time.
* **Hybrid Architecture:** Combines structured executive reporting tabs with unstructured, flexible AI intelligence.
* **Direct Filter Integration:** Full structural alignment between frontend sidebar filters (Region, Warehouse, Category, Date) and complex SQL aggregates without row duplication.
* **Raw Database Inspector:** Admin-level visibility layer executing safe, row-level queries directly to the backend to maintain data transparency and auditability.

---

## Core Analytical Modules

1.  **Category Winners:** Tracks top revenue-generating product categories and department codes.
2.  **Warehouse Battle:** Regional rank execution tracking performance metrics across multiple store locations.
3.  **Empty Shelf Alerts:** Live inventory monitor triggering automated workflow notifications ("Restock Now", "Out of Stock") based on dynamic reorder thresholds.
4.  **Hidden Failures:** Pinpoints overlapping points of lowest performance across paired Warehouse-Category intersections.
5.  **Inventory Health & Promotion Strategy:** Flags slow-moving stock and tracks overstocked capital stuck on shelves.

---

## Tech Stack & Database Architecture

* **Frontend:** Streamlit, Plotly Express
* **Backend Database:** PostgreSQL (`zava` database utilizing a custom 9-table `costco_analytics` schema)
* **ORM / Connection Engine:** SQLAlchemy, Psycopg2
* **AI Engine:** Google Generative AI (Gemini API)

---

## Quick Start

### 1. Clone the Repository
#```bash

git clone [https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git)

cd YOUR_REPO_NAME


### 2. Install Dependencies
pip install streamlit pandas plotly sqlalchemy psycopg2-binary google-generativeai


### 3. Environment Setup
[postgres]
host = "localhost"
port = "5432"
database = "zava"
user = "postgres"
password = "YOUR_PASSWORD"

GOOGLE_API_KEY = "YOUR_GEMINI_API_KEY"

### 4. Run the Application
streamlit run your_script_name.py

