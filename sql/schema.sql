-- Create the hotdeals table
create table public.hotdeals (
  id text not null,
  source text not null,
  title text not null,
  link text not null,
  original_price text,
  discount_price text,
  currency text default 'KRW',
  posted_at timestamptz not null,
  author text,
  votes int default 0,
  comment_count int default 0,
  image_url text,
  is_hotdeal boolean,
  why_hotdeal text,
  category text,
  created_at timestamptz default now(),
  constraint hotdeals_pkey primary key (id, source)
);

-- Separate index if needed (though PK covers id/source)
create index idx_posted_at on public.hotdeals (posted_at);
