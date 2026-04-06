import pytest
from evaluate_grading import calculate_alignment_score, evaluate_system_performance

def test_calculate_alignment_score_perfect_match():
    # System confidence 10 (normalizes to 5), User grade 5 -> Difference 0 -> 100%
    assert calculate_alignment_score(10, 5) == 100.0

def test_calculate_alignment_score_perfect_mismatch():
    # System confidence 10 (normalizes to 5), User grade 1 -> Difference 4 -> 0%
    assert calculate_alignment_score(10, 1) == 0.0

def test_calculate_alignment_score_partial_match():
    # System confidence 8 (normalizes to 4), User grade 2 -> Difference 2 -> 50%
    assert calculate_alignment_score(8, 2) == 50.0
    
    # System confidence 5 (normalizes to 2.5), User grade 4 -> Difference 1.5 -> 62.5%
    assert calculate_alignment_score(5, 4) == 62.5

def test_calculate_alignment_score_none_values():
    assert calculate_alignment_score(None, 5) == 0.0
    assert calculate_alignment_score(10, None) == 0.0
    assert calculate_alignment_score(None, None) == 0.0

def test_evaluate_system_performance(mocker):
    # Mock psycopg2 connect and cursor
    mock_connect = mocker.patch('evaluate_grading.psycopg2.connect')
    mock_conn = mock_connect.return_value
    mock_cur = mock_conn.cursor.return_value
    
    # Mock database returning 2 graded profiles:
    # 1. Perfect match (10/10 confidence, 5/5 user grade)
    # 2. Perfect mismatch (10/10 confidence, 1/5 user grade)
    mock_cur.fetchall.return_value = [
        ("id1", "John", "Doe", 10, 5),
        ("id2", "Jane", "Smith", 10, 1)
    ]
    
    average_accuracy = evaluate_system_performance()
    
    # Expected average: (100% + 0%) / 2 = 50.0%
    assert average_accuracy == 50.0

def test_evaluate_system_performance_no_data(mocker):
    mock_connect = mocker.patch('evaluate_grading.psycopg2.connect')
    mock_conn = mock_connect.return_value
    mock_cur = mock_conn.cursor.return_value
    
    # Mock empty database return
    mock_cur.fetchall.return_value = []
    
    average_accuracy = evaluate_system_performance()
    assert average_accuracy is None
