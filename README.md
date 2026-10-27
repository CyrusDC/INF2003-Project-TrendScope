## 🚀 TrendScope: Polyglot Persistence Analytics Platform
Application Overview
TrendScope is an advanced, full-stack database application designed to analyze and surface real-time insights from multi-region trending video statistics. By adopting a polyglot persistence architecture, TrendScope strategically separates its workload across two distinct database engines—leveraging a relational model for structured entity mapping and a non-relational document store for high-volume time-series metrics and nested attributes.

Key Features & Database Architecture
TrendScope splits its business logic across a Python Flask backend and an interactive Streamlit graphical interface, routing operations to the database best optimized for the task:

1. Relational Backend (PostgreSQL / AWS)
Purpose: Manages rigid core entities, strict foreign key constraints, and normalized relationships.

Schema Design: Features an Entity-Relationship (ER) model encompassing 1-to-Many (1:N) and Many-to-Many (M:N) connections across Channels, Categories, Videos, and Trending Regions.

Advanced Features: Utilizes complex SQL views, aggregate functions, and window operations to calculate channel performance rankings, category view distributions, and cross-region trends.

2. Non-Relational Backend (MongoDB Atlas / NoSQL)
Purpose: Handles flexible, high-volume unstructured monetization logs, nested country performance arrays, and fluctuating daily attributes.

Schema Design: Document-oriented BSON schema storing nested sub-documents and dynamic metrics without rigid column constraints.

Advanced Features: Implements complex MongoDB Aggregation Pipelines ($unwind, $group, $sum, $avg) to execute real-time analytical queries:

Global Ad Revenue Analysis: Dynamically unpacks and aggregates estimated ad revenues grouped by country code (country_code).

Creator Tier Evaluation: Evaluates whether larger channels (creator_tier: large, medium, small) command a higher financial return through statistical grouping.

Category & Content Breakdown: Provides rapid document filtering and breakdown metrics across various content classifications.

3. Interactive Presentation Layer (Streamlit & Flask REST API)
A clean, user-friendly graphical interface built with Streamlit that communicates asynchronously with the Flask backend via HTTP requests using Python's requests library.

Eliminates the need for manual SQL/NoSQL command-line queries, providing a seamless dashboard experience with instant data visualization tables.

Tech Stack
Frontend: Streamlit, Pandas, Python

Backend API: Python Flask, Pymongo, Psycopg2, Python-Dotenv

Databases: PostgreSQL (Relational), MongoDB Atlas / Document Store (NoSQL)

Infrastructure & Version Control: Docker / Docker Compose (for local container fallback), Git & GitHub
