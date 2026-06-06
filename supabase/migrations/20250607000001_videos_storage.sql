-- Supabase Storage bucket for rendered videos (streamed in app, downloaded on demand)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('videos', 'videos', true, 52428800, ARRAY['video/mp4']::text[])
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "Public video read"
ON storage.objects FOR SELECT
USING (bucket_id = 'videos');

CREATE POLICY "Authenticated video upload"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'videos');

CREATE POLICY "Authenticated video update"
ON storage.objects FOR UPDATE
USING (bucket_id = 'videos');
