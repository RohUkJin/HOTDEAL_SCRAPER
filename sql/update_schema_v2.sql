-- Add AI enrichment columns to hotdeals table
ALTER TABLE hotdeals 
ADD COLUMN IF NOT EXISTS sentiment_score INTEGER,
ADD COLUMN IF NOT EXISTS tags TEXT[],
ADD COLUMN IF NOT EXISTS report_count INTEGER DEFAULT 0;
