-- 1. Reset Data (Optional, comment out if you want to keep data)
-- TRUNCATE TABLE public.hotdeals;

-- 2. Add missing columns to hotdeals table (Safe to run multiple times)
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS naver_price bigint;
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS savings bigint;
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS score float;
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS comments text[]; -- PostgreSQL array type for list of strings
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS why_hotdeal text;
ALTER TABLE public.hotdeals ADD COLUMN IF NOT EXISTS ai_summary text; -- New field for AI reasoning one-liner

-- Optional: Add comments for documentation
COMMENT ON COLUMN public.hotdeals.status IS 'Analysis status: HOT, DROP, READY, etc.';
COMMENT ON COLUMN public.hotdeals.score IS 'Hot deal score calculated by processor';
COMMENT ON COLUMN public.hotdeals.ai_summary IS 'One-line reason from AI';
