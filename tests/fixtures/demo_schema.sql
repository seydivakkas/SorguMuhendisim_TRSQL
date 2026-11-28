-- Synthetic demo database. All values are fictitious.
CREATE TABLE dealers (
  dealer_id   INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  city        TEXT NOT NULL,
  tax_number  TEXT              -- sensitive: denied for analyst role
);
CREATE TABLE sales (
  sale_id       INTEGER PRIMARY KEY,
  dealer_id     INTEGER NOT NULL REFERENCES dealers(dealer_id),
  sale_date     TEXT NOT NULL,
  total_amount  REAL NOT NULL,
  return_amount REAL NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'completed'
);
CREATE TABLE salaries (          -- not visible to analysts
  employee_id INTEGER PRIMARY KEY,
  amount      REAL NOT NULL
);

INSERT INTO dealers VALUES
  (1, 'Bayi A', 'Trabzon', '1111111111'),
  (2, 'Bayi B', 'Trabzon', '2222222222'),
  (3, 'Bayi C', 'Trabzon', '3333333333'),
  (4, 'Bayi D', 'Rize',    '4444444444'),
  (5, 'Bayi E', 'Trabzon', '5555555555');
INSERT INTO sales (dealer_id, sale_date, total_amount, return_amount, status) VALUES
  (1, '2026-10-05', 1000000, 0, 'completed'),
  (1, '2026-10-20',  250000, 0, 'completed'),
  (2, '2026-10-11',  980000, 0, 'completed'),
  (3, '2026-10-15',  820000, 0, 'completed'),
  (4, '2026-10-09',  999999, 0, 'completed'),
  (5, '2026-10-30',  510000, 0, 'completed'),
  (5, '2026-09-30',  900000, 0, 'completed'),
  (2, '2026-10-12',  100000, 0, 'cancelled');
INSERT INTO salaries VALUES (1, 50000);
