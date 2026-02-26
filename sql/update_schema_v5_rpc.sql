-- Create a match_hotdeals function to perform vector similarity search
-- You need to run this script in your Supabase SQL Editor.

CREATE OR REPLACE FUNCTION match_hotdeals(
    query_embedding vector(768),
    match_threshold float,
    match_count int,
    filter_categories text[] DEFAULT null
)
RETURNS SETOF hotdeals
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM hotdeals
    WHERE embedding IS NOT NULL
      AND report_count < 2
      AND (filter_categories IS NULL OR category = ANY(filter_categories))
      AND 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
