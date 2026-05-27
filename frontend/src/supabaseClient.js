import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  console.error(
    'Missing Supabase env vars. Make sure REACT_APP_SUPABASE_URL and ' +
    'REACT_APP_SUPABASE_ANON_KEY are set in your environment.'
  );
}

export const supabase = createClient(
  supabaseUrl  || 'missing-url',
  supabaseAnonKey || 'missing-key'
);
