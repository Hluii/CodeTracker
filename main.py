import argparse
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

from scraper import cookies_from_environment, scrape_question


DATABASE_PATH = Path(__file__).with_name("my_database.db")
VAULT_PATH = Path(__file__).with_name("vault")

test_submission = {
    "question_title": "Two Sum",
    "question_url": "https://leetcode.com/problems/two-sum/",
    "difficulty": "Easy",
    "tags": ["array", "hash-table"],
    "description": (
        "Given an array of integers `nums` and an integer `target`, "
        "return indices of the two numbers such that they add up to target."
    ),
    "submission_num": 1,
    "date": "2026-10-27",
    "time_to_complete": 360,
    "runtime_ms": 48,
    "memory_mb": 15.2,
    "time_complexity": "O(N)",
    "space_complexity": "O(N)",
    "code": """class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        seen = {}
        for i, num in enumerate(nums):
            remaining = target - num
            if remaining in seen:
                return [seen[remaining], i]
            seen[num] = i""",
}


def append_submission_to_vault(question: dict, submission: dict) -> Path:
    """Append a submission and its question metadata to a title-named note."""
    title = question["title"]
    if not isinstance(title, str) or not title.strip():
        raise ValueError("question title must be a non-empty string.")

    safe_title = re.sub(r'[<>:"/\\|?*]', "", title).strip().rstrip(".")
    if not safe_title:
        raise ValueError("question title must contain a valid filename.")

    VAULT_PATH.mkdir(parents=True, exist_ok=True)
    note_path = VAULT_PATH / f"{safe_title}.md"
    tags = ", ".join(tag.replace("-", " ").title() for tag in question["tags"])
    question_header = (
        f"# {question['id']}. {title}\n\n"
        f"- **LeetCode Link:** {question['url']}\n"
        f"- **Difficulty:** {question['difficulty']}\n"
        f"- **Topics:** {tags}\n\n"
        "## Brief Problem Description\n"
        f"{question['description']}\n\n"
        "---\n"
    )
    submission_section = (
        f"\n\n## Submission #{submission['submission_num']}: "
        f"{submission.get('approach', 'Solution')} (Python)\n"
        f"- **Date:** {submission['submitted_on']}\n"
        f"- **Time to Complete:** {submission['time_to_complete']} seconds\n"
        f"- **Time Complexity:** {submission['time_complexity']}\n"
        f"- **Space Complexity:** {submission['space_complexity']}\n\n"
        "```python\n"
        f"{submission['code']}\n"
        "```\n"
    )

    if note_path.exists() and note_path.stat().st_size > 0:
        with note_path.open("a", encoding="utf-8", newline="\n") as note:
            note.write(submission_section)
    else:
        note_path.write_text(
            question_header + submission_section,
            encoding="utf-8",
            newline="\n",
        )
    return note_path


def create_tables(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            difficulty TEXT NOT NULL CHECK (difficulty IN ('Easy', 'Medium', 'Hard')),
            tags TEXT NOT NULL DEFAULT '[]',
            description TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY,
            question_id INTEGER NOT NULL,
            submission_num INTEGER NOT NULL CHECK (submission_num > 0),
            submitted_on TEXT NOT NULL,
            time_to_complete INTEGER,
            runtime_ms INTEGER NOT NULL CHECK (runtime_ms >= 0),
            memory_mb REAL NOT NULL CHECK (memory_mb >= 0),
            time_complexity TEXT NOT NULL,
            space_complexity TEXT NOT NULL,
            code TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            UNIQUE (question_id, submission_num)
        );
        """
    )
    question_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(questions)")
    }
    if "description" not in question_columns:
        connection.execute(
            "ALTER TABLE questions ADD COLUMN description TEXT NOT NULL DEFAULT ''"
        )
    submission_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(submissions)")
    }
    if "time_to_complete" not in submission_columns:
        connection.execute(
            "ALTER TABLE submissions ADD COLUMN time_to_complete INTEGER"
        )


def ingest_submission(
    connection: sqlite3.Connection,
    scraped_question: dict,
    submission: dict,
) -> tuple[int, int]:
    connection.execute(
        """
        INSERT OR IGNORE INTO questions (
            id, title, url, difficulty, tags, description
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            scraped_question["question_id"],
            scraped_question["question_title"],
            scraped_question["question_url"],
            scraped_question["difficulty"],
            json.dumps(scraped_question["tags"]),
            scraped_question["description"],
        ),
    )
    question_row = connection.execute(
        "SELECT id FROM questions WHERE url = ?",
        (scraped_question["question_url"],),
    ).fetchone()
    if question_row is None:
        raise RuntimeError("The seeded question could not be found.")
    connection.execute(
        """
        UPDATE questions
        SET title = ?, difficulty = ?, tags = ?, description = ?
        WHERE id = ?
        """,
        (
            scraped_question["question_title"],
            scraped_question["difficulty"],
            json.dumps(scraped_question["tags"]),
            scraped_question["description"],
            question_row[0],
        ),
    )

    connection.execute(
        """
        INSERT OR IGNORE INTO submissions (
            question_id, submission_num, submitted_on, time_to_complete,
            runtime_ms, memory_mb, time_complexity, space_complexity, code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_row[0],
            submission["submission_num"],
            submission["date"],
            submission["time_to_complete"],
            submission["runtime_ms"],
            submission["memory_mb"],
            submission["time_complexity"],
            submission["space_complexity"],
            submission["code"],
        ),
    )
    connection.execute(
        """
        UPDATE submissions
        SET submitted_on = ?, time_to_complete = ?, runtime_ms = ?,
            memory_mb = ?, time_complexity = ?, space_complexity = ?, code = ?
        WHERE question_id = ? AND submission_num = ?
        """,
        (
            submission["date"],
            submission["time_to_complete"],
            submission["runtime_ms"],
            submission["memory_mb"],
            submission["time_complexity"],
            submission["space_complexity"],
            submission["code"],
            question_row[0],
            submission["submission_num"],
        ),
    )
    submission_row = connection.execute(
        """
        SELECT id FROM submissions
        WHERE question_id = ? AND submission_num = ?
        """,
        (question_row[0], submission["submission_num"]),
    ).fetchone()
    if submission_row is None:
        raise RuntimeError("The seeded submission could not be found.")
    return question_row[0], submission_row[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape a LeetCode question and ingest it into CodeTracker."
    )
    parser.add_argument(
        "title_slug",
        help="LeetCode problem slug, such as two-sum",
    )
    args = parser.parse_args()
    scraped_question = scrape_question(
        args.title_slug,
        cookies=cookies_from_environment(),
    )
    submission = {
        key: test_submission[key]
        for key in (
            "submission_num",
            "date",
            "time_to_complete",
            "runtime_ms",
            "memory_mb",
            "time_complexity",
            "space_complexity",
            "code",
        )
    }

    with sqlite3.connect(DATABASE_PATH) as connection:
        create_tables(connection)
        question_id, submission_id = ingest_submission(
            connection,
            scraped_question,
            submission,
        )
        question_row = connection.execute(
            "SELECT id, title, url, difficulty, tags, description "
            "FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        submission_row = connection.execute(
            "SELECT submission_num, submitted_on, time_to_complete, "
            "time_complexity, space_complexity, code "
            "FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if question_row is None or submission_row is None:
            raise RuntimeError("Seeded vault data could not be loaded.")
        questions_table = pd.read_sql_query(
                                            """
                                            SELECT id, title, url, difficulty, tags 
                                            FROM questions
                                            """, 
                                            connection)
        submissions_table = pd.read_sql_query(
                                        """
                                        SELECT id, question_id, submission_num, submitted_on,
                                            time_to_complete, runtime_ms, memory_mb,
                                            time_complexity, space_complexity
                                        FROM submissions
                                        """, 
                                        connection)
        print("Questions:")
        print(questions_table.to_string(index=False))
        print("\nSubmissions:")
        print(submissions_table.to_string(index=False))

    question = {
        "id": question_row[0],
        "title": question_row[1],
        "url": question_row[2],
        "difficulty": question_row[3],
        "tags": json.loads(question_row[4]),
        "description": question_row[5],
    }
    submission = {
        "submission_num": submission_row[0],
        "submitted_on": submission_row[1],
        "time_to_complete": submission_row[2],
        "time_complexity": submission_row[3],
        "space_complexity": submission_row[4],
        "code": submission_row[5],
    }
    append_submission_to_vault(question, submission)


if __name__ == "__main__":
    main()
