INSERT OR IGNORE INTO departments VALUES (1,'Computer Science'),(2,'Mathematics'),(3,'Physics');
INSERT OR IGNORE INTO students VALUES (1,'Asha Rao','asha@example.edu',1),(2,'Ben Joseph','ben@example.edu',1),(3,'Chitra Nair','chitra@example.edu',2),(4,'Dev Patel','dev@example.edu',3),(5,'Esha Singh','esha@example.edu',2);
INSERT OR IGNORE INTO instructors VALUES (1,'Dr. Meera Shah',1),(2,'Dr. Arun Das',2),(3,'Dr. Leena Roy',3);
INSERT OR IGNORE INTO courses VALUES (1,'CS101','Database Systems',4,1,1),(2,'CS202','Artificial Intelligence',4,1,1),(3,'MA101','Calculus',3,2,2),(4,'PH101','Mechanics',3,3,3);
INSERT OR IGNORE INTO enrollments VALUES (1,1,1,'2026 Spring','2026-01-10'),(2,2,1,'2026 Spring','2026-01-10'),(3,1,2,'2026 Spring','2026-01-10'),(4,3,3,'2026 Spring','2026-01-10'),(5,5,3,'2026 Spring','2026-01-10'),(6,4,4,'2026 Spring','2026-01-10');
INSERT OR IGNORE INTO examinations VALUES (1,1,'Final','2026-04-20'),(2,2,'Final','2026-04-22'),(3,3,'Final','2026-04-24'),(4,4,'Final','2026-04-25');
INSERT OR IGNORE INTO marks VALUES (1,1,1,91),(2,1,2,78),(3,2,1,88),(4,3,3,84),(5,3,5,93),(6,4,4,76);

