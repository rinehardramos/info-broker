import os
import psycopg2
import pandas as pd
import argparse
import warnings
from openai import OpenAI
from dotenv import load_dotenv
import json

from security import escape_dataframe_cells

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

load_dotenv()

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
CHAT_MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "local-model")

DB_NAME = os.getenv("POSTGRES_DB", "auto_marketer")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5433")

openai_client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)

def setup_postgres():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cur = conn.cursor()
    # Add a column for the generated email
    cur.execute("""
        ALTER TABLE linkedin_profiles 
        ADD COLUMN IF NOT EXISTS generated_email TEXT
    """)
    conn.commit()
    return conn

def generate_email_for_profile(profile):
    """Uses the LLM to write a personalized cold email based on research."""
    first_name = profile['first_name']
    last_name = profile['last_name']
    company = profile.get('company', 'your company')
    research_summary = profile['research_summary']
    
    prompt = f"""
    You are an expert B2B sales development representative. 
    Write a highly personalized, concise cold email to the following prospect.
    
    Prospect Name: {first_name} {last_name}
    Company: {company}
    Research Context: {research_summary}
    
    Goal: We offer elite offshore product development teams and Virtual Assistants to help SMBs scale without high overhead costs.
    Tone: Professional, direct, and focused on value. Do not be overly salesy. 
    
    Output ONLY the email subject line and body. Do not include commentary.
    """
    
    print(f"  [LLM] Generating email for {first_name} {last_name} at {company}...")
    try:
        response = openai_client.chat.completions.create(
            model=CHAT_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are an expert SDR writing cold emails."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [LLM] Error generating email: {e}")
        return None

def process_and_generate_emails():
    conn = setup_postgres()
    cur = conn.cursor()
    
    # Target criteria: SMB owners who have completed research
    cur.execute("""
        SELECT id, first_name, last_name, headline, raw_data, research_summary, generated_email
        FROM linkedin_profiles
        WHERE research_status = 'completed' AND is_smb = TRUE
    """)
    
    profiles = cur.fetchall()
    
    updated_count = 0
    for row in profiles:
        prof_id, first_name, last_name, headline, raw_data, research_summary, generated_email = row
        
        # Only generate if we haven't already
        if not generated_email:
            # Extract company from raw data
            company = "your company"
            if isinstance(raw_data, dict) and raw_data.get('currentPosition'):
                company = raw_data['currentPosition'][0].get('companyName') or company
                
            profile_dict = {
                'first_name': first_name,
                'last_name': last_name,
                'company': company,
                'research_summary': research_summary
            }
            
            email_text = generate_email_for_profile(profile_dict)
            if email_text:
                cur.execute("""
                    UPDATE linkedin_profiles 
                    SET generated_email = %s 
                    WHERE id = %s
                """, (email_text, prof_id))
                conn.commit()
                updated_count += 1
                
    print(f"\\n✅ Generated {updated_count} new emails.")
    conn.close()

def fetch_qualified_data():
    """Fetches profiles that have generated emails."""
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
                first_name, 
                last_name, 
                headline,
                research_summary,
                generated_email,
                raw_data
            FROM linkedin_profiles
            WHERE generated_email IS NOT NULL
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None

def extract_light_data(df):
    """Extracts only the critical info + generated email."""
    df['linkedin_url'] = df['raw_data'].apply(lambda x: x.get('linkedinUrl') if isinstance(x, dict) else None)
    df['emails'] = df['raw_data'].apply(
        lambda x: ', '.join([e.get('email', '') if isinstance(e, dict) else str(e) for e in x.get('emails', [])]) 
        if isinstance(x, dict) and x.get('emails') else None
    )
    df['company_websites'] = df['raw_data'].apply(
        lambda x: ', '.join([w.get('url', '') if isinstance(w, dict) else str(w) for w in x.get('companyWebsites', [])]) 
        if isinstance(x, dict) and x.get('companyWebsites') else None
    )
    
    def get_company(x):
        if isinstance(x, dict) and x.get('currentPosition'):
            return x['currentPosition'][0].get('companyName')
        return None
        
    df['company_name'] = df['raw_data'].apply(get_company)
    
    return df.drop(columns=['raw_data'])

def export_csv(df, output_file):
    flat_df = escape_dataframe_cells(extract_light_data(df))
    flat_df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"✅ Successfully exported {len(df)} target profiles to {output_file}")

def export_xlsx(df, output_file):
    flat_df = escape_dataframe_cells(extract_light_data(df))
    flat_df.to_excel(output_file, index=False, engine='openpyxl')
    print(f"✅ Successfully exported {len(df)} target profiles to {output_file}")

def export_json(df, output_file):
    flat_df = extract_light_data(df)
    records = flat_df.to_dict(orient='records')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=4, ensure_ascii=False)
    print(f"✅ Successfully exported {len(df)} target profiles to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Emails and Export Target Profiles")
    parser.add_argument('--format', choices=['json', 'csv', 'xlsx'], required=True, help="Export format")
    parser.add_argument('--output', default='targeted_campaign', help="Output filename prefix")
    args = parser.parse_args()

    print("Step 1: Generating emails for qualified SMB prospects...")
    process_and_generate_emails()
    
    print("\\nStep 2: Fetching target profiles...")
    df = fetch_qualified_data()
    
    if df is None or df.empty:
        print("No qualified profiles found with generated emails.")
    else:
        output_filename = f"{args.output}.{args.format}"
        if args.format == 'json':
            export_json(df, output_filename)
        elif args.format == 'csv':
            export_csv(df, output_filename)
        elif args.format == 'xlsx':
            export_xlsx(df, output_filename)
