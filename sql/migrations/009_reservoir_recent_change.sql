-- 12 h and 48 h changes on now.reservoir_status, next to the 6, 24 and 72 h ones: while it rains, the page shows how the
-- water behind a tap, a basin or the country has moved in the last 6, 12, 24 and 48 hours.

ALTER TABLE embalses."now".reservoir_status ADD COLUMN change_12h_hm3 DOUBLE;
ALTER TABLE embalses."now".reservoir_status ADD COLUMN change_48h_hm3 DOUBLE;
COMMENT ON COLUMN embalses."now".reservoir_status.change_12h_hm3 IS 'Change over 12 hours, hm³ (live stations only).';
COMMENT ON COLUMN embalses."now".reservoir_status.change_48h_hm3 IS 'Change over 48 hours, hm³ (live stations only).';
