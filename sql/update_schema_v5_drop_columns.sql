-- Drop unused columns from hotdeals table
ALTER TABLE public.hotdeals
DROP COLUMN IF EXISTS author,
DROP COLUMN IF EXISTS why_hotdeal,
DROP COLUMN IF EXISTS tags,
DROP COLUMN IF EXISTS original_price,
DROP COLUMN IF EXISTS image_url;
