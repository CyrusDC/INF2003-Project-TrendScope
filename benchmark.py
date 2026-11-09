import time
import os
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from data_manager import DataManager

load_dotenv()

def run_benchmarks(iterations=50):
    print(f"[*] Starting SQL vs. NoSQL Benchmark ({iterations} iterations per test)...")
    
    # 1. Fetch sample IDs from DB to ensure valid queries
    conn = DataManager.get_pg_connection()
    cur = conn.cursor()
    cur.execute("SELECT video_id FROM Video LIMIT 10;")
    sample_video_ids = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not sample_video_ids:
        sample_video_ids = ["test_id_001"]

    test_vid = sample_video_ids[0]

    mongo_col = DataManager.get_mongo_collection("revenue")

    results = []

    # -------------------------------------------------------------
    # TEST 1: Single Record Point Lookup (by video_id)
    # -------------------------------------------------------------
    print("[1/4] Running Point Lookup Benchmark...")
    sql_times = []
    nosql_times = []

    for _ in range(iterations):
        # SQL
        conn = DataManager.get_pg_connection()
        t0 = time.perf_counter()
        pd.read_sql("SELECT * FROM Video WHERE video_id = %s;", conn, params=(test_vid,))
        t1 = time.perf_counter()
        conn.close()
        sql_times.append((t1 - t0) * 1000)

        # NoSQL
        t0 = time.perf_counter()
        _ = mongo_col.find_one({"video_id": test_vid})
        t1 = time.perf_counter()
        nosql_times.append((t1 - t0) * 1000)

    results.append({
        "Scenario": "1. Point Lookup (Single ID)",
        "PostgreSQL (ms)": round(sum(sql_times) / len(sql_times), 2),
        "MongoDB (ms)": round(sum(nosql_times) / len(nosql_times), 2)
    })

    # -------------------------------------------------------------
    # TEST 2: Filtered Query / Range Scan
    # -------------------------------------------------------------
    print("[2/4] Running Filtered Query Benchmark...")
    sql_times = []
    nosql_times = []

    sql_filter = "SELECT * FROM Video WHERE tag_count > 10 LIMIT 100;"

    for _ in range(iterations):
        # SQL
        conn = DataManager.get_pg_connection()
        t0 = time.perf_counter()
        pd.read_sql(sql_filter, conn)
        t1 = time.perf_counter()
        conn.close()
        sql_times.append((t1 - t0) * 1000)

        # NoSQL
        t0 = time.perf_counter()
        _ = list(mongo_col.find({"creator_tier": "large"}).limit(100))
        t1 = time.perf_counter()
        nosql_times.append((t1 - t0) * 1000)

    results.append({
        "Scenario": "2. Filtered Range Scan",
        "PostgreSQL (ms)": round(sum(sql_times) / len(sql_times), 2),
        "MongoDB (ms)": round(sum(nosql_times) / len(nosql_times), 2)
    })

    # -------------------------------------------------------------
    # TEST 3: Complex Aggregation
    # -------------------------------------------------------------
    print("[3/4] Running Aggregation Benchmark...")
    sql_times = []
    nosql_times = []

    sql_agg = """
        SELECT c.category_name, COUNT(v.video_id) AS total_videos, AVG(tr.views) AS avg_views
        FROM Video v
        JOIN Category c ON v.category_id = c.category_id
        JOIN Trending_Record tr ON v.video_id = tr.video_id
        GROUP BY c.category_name;
    """

    mongo_agg = [
        {"$unwind": "$revenue_by_country"},
        {"$group": {
            "_id": "$revenue_by_country.country_code",
            "total_estimated_revenue": {"$sum": "$revenue_by_country.estimated_gross_usd"}
        }}
    ]

    for _ in range(iterations):
        # SQL
        conn = DataManager.get_pg_connection()
        t0 = time.perf_counter()
        pd.read_sql(sql_agg, conn)
        t1 = time.perf_counter()
        conn.close()
        sql_times.append((t1 - t0) * 1000)

        # NoSQL
        t0 = time.perf_counter()
        _ = list(mongo_col.aggregate(mongo_agg))
        t1 = time.perf_counter()
        nosql_times.append((t1 - t0) * 1000)

    results.append({
        "Scenario": "3. Aggregation (Join vs $unwind)",
        "PostgreSQL (ms)": round(sum(sql_times) / len(sql_times), 2),
        "MongoDB (ms)": round(sum(nosql_times) / len(nosql_times), 2)
    })

    # -------------------------------------------------------------
    # TEST 4: Batch Upsert (10 records)
    # -------------------------------------------------------------
    print("[4/4] Running Batch Upsert Benchmark...")
    sql_times = []
    nosql_times = []

    batch_dummy_sql = [
        {"cat_id": 990 + i, "cat_name": f"Test Bench {i}"} for i in range(10)
    ]
    batch_dummy_mongo = [
        {"video_id": f"bench_{i:04d}", "creator_tier": "bench", "category_id": 99} for i in range(10)
    ]

    for _ in range(max(5, iterations // 5)):
        # SQL
        t0 = time.perf_counter()
        DataManager.bulk_upsert_postgres("Category", batch_dummy_sql)
        t1 = time.perf_counter()
        sql_times.append((t1 - t0) * 1000)

        # NoSQL
        t0 = time.perf_counter()
        DataManager.bulk_upsert_mongo_revenue(batch_dummy_mongo)
        t1 = time.perf_counter()
        nosql_times.append((t1 - t0) * 1000)

    results.append({
        "Scenario": "4. Batch Upsert (10 items)",
        "PostgreSQL (ms)": round(sum(sql_times) / len(sql_times), 2),
        "MongoDB (ms)": round(sum(nosql_times) / len(nosql_times), 2)
    })

    # Clean up test benchmark rows
    conn = DataManager.get_pg_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM Category WHERE category_id >= 990;")
    conn.commit()
    cur.close()
    conn.close()
    mongo_col.delete_many({"creator_tier": "bench"})

    # Print summary table in terminal
    df_results = pd.DataFrame(results)
    print("\n================== BENCHMARK SUMMARY (Avg Latency in ms) ==================")
    print(df_results.to_string(index=False))
    print("===========================================================================\n")

    # Generate Chart
    generate_chart(df_results)
    return df_results

def generate_chart(df):
    plt.style.use('ggplot')
    fig, ax = plt.subplots(figsize=(10, 5))

    x = range(len(df))
    width = 0.35

    bar1 = ax.bar([i - width/2 for i in x], df["PostgreSQL (ms)"], width, label='PostgreSQL (AWS RDS)', color='#007acc')
    bar2 = ax.bar([i + width/2 for i in x], df["MongoDB (ms)"], width, label='MongoDB Atlas', color='#13aa52')

    ax.set_ylabel('Average Latency (Milliseconds - Lower is Better)')
    ax.set_title('Database Performance Benchmark: PostgreSQL vs MongoDB Atlas', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(df["Scenario"], rotation=15, ha="right")
    ax.legend()

    # Add numeric labels on bars
    for bar in bar1 + bar2:
        yval = bar.get_height()
        ax.annotate(f'{yval:.1f}ms',
                    xy=(bar.get_x() + bar.get_width() / 2, yval),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    output_path = "benchmark_results.png"
    plt.savefig(output_path, dpi=300)
    print(f"[✓] Benchmark comparison chart saved to: {output_path}")

if __name__ == "__main__":
    run_benchmarks(iterations=30)