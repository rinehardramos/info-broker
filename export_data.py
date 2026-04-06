import os
import psycopg2
import json
import pandas as pd
import argparse
import warnings
from dotenv import load_dotenv

from security import escape_dataframe_cells

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

load_dotenv()

DB_NAME = os.getenv("POSTGRES_DB", "auto_marketer")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5433")

def fetch_data():
    """Fetches all processed profiles from PostgreSQL."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        query = """
            SELECT 
                id, 
                first_name, 
                last_name, 
                headline,
                research_status,
                is_smb,
                needs_outsourcing_prob,
                needs_cheap_labor_prob,
                searching_vendors_prob,
                research_summary,
                system_confidence_score,
                confidence_rationale,
                search_queries_used,
                user_grade,
                user_feedback,
                raw_data
            FROM linkedin_profiles
            WHERE research_status IN ('completed', 'failed')
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None

def flatten_raw_data(df, mode='full'):
    """Flattens the nested 'raw_data' JSONB column."""
    if mode == 'light':
        # Extract only the most relevant fields
        df['apify_linkedinUrl'] = df['raw_data'].apply(lambda x: x.get('linkedinUrl') if isinstance(x, dict) else None)
        df['apify_emails'] = df['raw_data'].apply(
            lambda x: ', '.join([e.get('email', '') if isinstance(e, dict) else str(e) for e in x.get('emails', [])]) 
            if isinstance(x, dict) and x.get('emails') else None
        )
        df['apify_companyWebsites'] = df['raw_data'].apply(
            lambda x: ', '.join([w.get('url', '') if isinstance(w, dict) else str(w) for w in x.get('companyWebsites', [])]) 
            if isinstance(x, dict) and x.get('companyWebsites') else None
        )
        df['apify_connectionsCount'] = df['raw_data'].apply(lambda x: x.get('connectionsCount') if isinstance(x, dict) else None)
        
        # Attempt to get company name
        def get_company(x):
            if isinstance(x, dict) and x.get('currentPosition'):
                return x['currentPosition'][0].get('companyName')
            return None
            
        df['apify_currentCompany'] = df['raw_data'].apply(get_company)
        
        return df.drop(columns=['raw_data'])
    else:
        # Full mode: expand everything
        raw_df = pd.json_normalize(df['raw_data'])
        raw_df = raw_df.add_prefix('apify_')
        return df.drop(columns=['raw_data']).join(raw_df)

def export_json(df, output_file, mode='full'):
    if mode == 'light':
        df = flatten_raw_data(df, mode='light')
    
    records = df.to_dict(orient='records')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=4, ensure_ascii=False)
    print(f"✅ Successfully exported {len(df)} records to {output_file} (Mode: {mode})")

def export_csv(df, output_file, mode='full'):
    flat_df = escape_dataframe_cells(flatten_raw_data(df, mode))
    flat_df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"✅ Successfully exported {len(df)} records to {output_file} (Mode: {mode})")

def export_xlsx(df, output_file, mode='full'):
    flat_df = escape_dataframe_cells(flatten_raw_data(df, mode))
    flat_df.to_excel(output_file, index=False, engine='openpyxl')
    print(f"✅ Successfully exported {len(df)} records to {output_file} (Mode: {mode})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Enriched Profiles from PostgreSQL")
    parser.add_argument('--format', choices=['json', 'csv', 'xlsx'], required=True, help="Export format")
    parser.add_argument('--output', default='export', help="Output filename prefix (without extension)")
    parser.add_argument('--mode', choices=['full', 'light'], default='full', help="Export mode (full vs light/condensed data)")
    args = parser.parse_args()

    print(f"Fetching data from PostgreSQL for {args.mode} export...")
    df = fetch_data()
    
    if df is None or df.empty:
        print("No processed profiles found in the database. Run `research_agent.py --run` first.")
    else:
        output_filename = f"{args.output}_{args.mode}.{args.format}"
        if args.format == 'json':
            export_json(df, output_filename, args.mode)
        elif args.format == 'csv':
            export_csv(df, output_filename, args.mode)
        elif args.format == 'xlsx':
            export_xlsx(df, output_filename, args.mode)
