-- Add embed_text column to hotdeals table for vector search
ALTER TABLE public.hotdeals 
ADD COLUMN IF NOT EXISTS embed_text TEXT;

-- Optional: Add comment for documentation
COMMENT ON COLUMN public.hotdeals.embed_text IS 'Nouns-only text for Gemini embedding generation';
