ALTER TABLE drug
  ADD COLUMN variant_type VARCHAR(20) NULL,
  ADD COLUMN stock_group_code VARCHAR(36) NULL,
  ADD COLUMN unit_amount INT NULL,
  ADD COLUMN base_name VARCHAR(128) NULL;

CREATE INDEX ix_drug_stock_group_code ON drug (stock_group_code);

CREATE TABLE drug_stock_group (
  id INT AUTO_INCREMENT PRIMARY KEY,
  group_code VARCHAR(36) NOT NULL,
  batch_no VARCHAR(50) NOT NULL,
  base_name VARCHAR(128) NOT NULL,
  unit_name VARCHAR(20) NOT NULL,
  total_units INT NOT NULL,
  pack_amount INT NOT NULL,
  retail_amount INT NULL,
  pack_drug_id INT NOT NULL,
  retail_drug_id INT NULL,
  created_by INT NULL,
  created_at DATETIME NULL,
  CONSTRAINT uq_drug_stock_group_group_code UNIQUE (group_code),
  CONSTRAINT fk_drug_stock_group_pack_drug FOREIGN KEY (pack_drug_id) REFERENCES drug(id),
  CONSTRAINT fk_drug_stock_group_retail_drug FOREIGN KEY (retail_drug_id) REFERENCES drug(id),
  CONSTRAINT fk_drug_stock_group_created_by FOREIGN KEY (created_by) REFERENCES user(id)
);

CREATE INDEX ix_drug_stock_group_batch_no ON drug_stock_group (batch_no);
CREATE INDEX ix_drug_stock_group_base_name ON drug_stock_group (base_name);

