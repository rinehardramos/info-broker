import psycopg2
import os
from dotenv import load_dotenv

def calculate_alignment_score(system_confidence, user_grade):
    """
    Calculates how well the system's self-confidence aligns with the user's ground-truth grade.
    system_confidence is 1-10.
    user_grade is 1-5.
    """
    if system_confidence is None or user_grade is None:
        return 0.0
        
    # Normalize system confidence to 1-5 scale (from 1-10)
    normalized_sys_conf = system_confidence / 2.0
    
    # Calculate the absolute difference between what the system thought and what the user graded
    difference = abs(normalized_sys_conf - user_grade)
    
    # Calculate percentage alignment
    # Max possible difference is 4 (e.g. system confidence 10 [normalized 5], user grade 1)
    # If difference is 0, score is 100%. If difference is 4, score is 0%.
    accuracy = max(0, 100 - (difference / 4.0 * 100))
    return round(accuracy, 2)

def evaluate_system_performance():
    load_dotenv()
    
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "auto_marketer"),
            user=os.getenv("POSTGRES_USER", "user"),
            password=os.getenv("POSTGRES_PASSWORD", "password"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432")
        )
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, first_name, last_name, system_confidence_score, user_grade 
            FROM linkedin_profiles 
            WHERE system_confidence_score IS NOT NULL AND user_grade IS NOT NULL
        """)
        
        rows = cur.fetchall()
        if not rows:
            print("No graded data found to evaluate. Please use `research_agent.py --grade` first.")
            return None
            
        print(f"Evaluating System vs. User grading alignment for {len(rows)} profiles:\\n")
        
        total_accuracy = 0
        for row in rows:
            prof_id, first_name, last_name, sys_conf, usr_grade = row
            acc = calculate_alignment_score(sys_conf, usr_grade)
            total_accuracy += acc
            print(f"- {first_name} {last_name}: System Confidence {sys_conf}/10 | User Grade {usr_grade}/5 --> Alignment: {acc}%")
            
        average_accuracy = total_accuracy / len(rows)
        print(f"\\n=====================================")
        print(f"OVERALL SYSTEM GRADING ACCURACY: {average_accuracy:.2f}%")
        print(f"=====================================")
        
        return average_accuracy
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return None

if __name__ == '__main__':
    evaluate_system_performance()
