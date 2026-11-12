PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS departments (department_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS students (student_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE, department_id INTEGER NOT NULL REFERENCES departments(department_id));
CREATE TABLE IF NOT EXISTS instructors (instructor_id INTEGER PRIMARY KEY, name TEXT NOT NULL, department_id INTEGER NOT NULL REFERENCES departments(department_id));
CREATE TABLE IF NOT EXISTS courses (course_id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL, credits INTEGER NOT NULL, department_id INTEGER NOT NULL REFERENCES departments(department_id), instructor_id INTEGER REFERENCES instructors(instructor_id));
CREATE TABLE IF NOT EXISTS enrollments (enrollment_id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(student_id), course_id INTEGER NOT NULL REFERENCES courses(course_id), semester TEXT NOT NULL, enrolled_on TEXT NOT NULL, UNIQUE(student_id, course_id, semester));
CREATE TABLE IF NOT EXISTS examinations (exam_id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(course_id), exam_type TEXT NOT NULL, exam_date TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marks (mark_id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES examinations(exam_id), student_id INTEGER NOT NULL REFERENCES students(student_id), score REAL NOT NULL CHECK(score >= 0 AND score <= 100), UNIQUE(exam_id, student_id));

