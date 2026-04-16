-- SupoClip — PostgreSQL schema (fresh database)
--
-- Source: pg_dump --schema-only from a live DB (PostgreSQL 16) aligned with:
--   - frontend/prisma/schema.prisma
--   - backend raw SQL repositories
--
-- Tasks table includes professional_hotwords + bilingual_subtitles_mode (Prisma migrations
-- 20260415123000 / 20260415140000) so new installs match the app without extra ALTERs.
--
-- Usage: create empty database, then:
--   psql -v ON_ERROR_STOP=1 -d your_db -f init.sql
--
-- Requires: PostgreSQL 14+ (trigger syntax). uuid-ossp extension.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

-- Prisma migration history (optional; Prisma migrate will create if missing)
CREATE TABLE public._prisma_migrations (
    id character varying(36) NOT NULL,
    checksum character varying(64) NOT NULL,
    finished_at timestamp with time zone,
    migration_name character varying(255) NOT NULL,
    logs text,
    rolled_back_at timestamp with time zone,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_steps_count integer DEFAULT 0 NOT NULL
);

CREATE TABLE public.users (
    id text NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    email text NOT NULL,
    password_hash character varying(255),
    name text NOT NULL,
    "emailVerified" boolean DEFAULT false NOT NULL,
    image text,
    "createdAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp with time zone NOT NULL,
    plan character varying(20) DEFAULT 'free'::character varying NOT NULL,
    subscription_status character varying(20) DEFAULT 'inactive'::character varying NOT NULL,
    stripe_customer_id character varying(255),
    stripe_subscription_id character varying(255),
    billing_period_start timestamp with time zone,
    billing_period_end timestamp with time zone,
    trial_ends_at timestamp with time zone,
    is_admin boolean DEFAULT false NOT NULL,
    default_font_family character varying(100) DEFAULT 'TikTokSans-Regular'::character varying,
    default_font_size integer DEFAULT 24,
    default_font_color character varying(7) DEFAULT '#FFFFFF'::character varying,
    notify_on_completion boolean DEFAULT true NOT NULL
);

COMMENT ON COLUMN public.users.notify_on_completion IS 'Whether to email the user when clip generation completes';

CREATE TABLE public.sources (
    id text NOT NULL,
    type character varying(20) NOT NULL,
    title character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    url character varying(1000)
);

CREATE TABLE public.tasks (
    id text NOT NULL,
    user_id text NOT NULL,
    source_id text,
    generated_clips_ids text[],
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    font_family character varying(100) DEFAULT 'TikTokSans-Regular'::character varying,
    font_size integer DEFAULT 24,
    font_color character varying(7) DEFAULT '#FFFFFF'::character varying,
    completion_notification_sent_at timestamp with time zone,
    processing_mode character varying(20) DEFAULT 'fast'::character varying NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    cache_hit boolean DEFAULT false NOT NULL,
    error_code character varying(80),
    stage_timings_json text,
    progress integer DEFAULT 0,
    progress_message text,
    audio_fade_in boolean DEFAULT false,
    audio_fade_out boolean DEFAULT false,
    caption_template character varying(50) DEFAULT 'default'::character varying,
    include_broll boolean DEFAULT false,
    chunk_size integer DEFAULT 15000,
    language character varying(10) DEFAULT 'auto'::character varying,
    professional_hotwords text,
    bilingual_subtitles_mode character varying(10) DEFAULT 'auto'::character varying NOT NULL,
    burn_clip_title_zh boolean DEFAULT true NOT NULL,
    target_clip_count integer,
    clip_theme text,
    CONSTRAINT tasks_progress_check CHECK (((progress >= 0) AND (progress <= 100)))
);

COMMENT ON COLUMN public.tasks.completion_notification_sent_at IS 'When the completion email was successfully sent';
COMMENT ON COLUMN public.tasks.progress IS 'Task progress percentage (0-100)';
COMMENT ON COLUMN public.tasks.progress_message IS 'Human-readable progress message';

CREATE TABLE public.generated_clips (
    id character varying(36) DEFAULT (public.uuid_generate_v4())::text NOT NULL,
    task_id character varying(36) NOT NULL,
    filename character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    start_time character varying(20) NOT NULL,
    end_time character varying(20) NOT NULL,
    duration double precision NOT NULL,
    text text,
    relevance_score double precision NOT NULL,
    reasoning text,
    clip_order integer NOT NULL,
    virality_score integer DEFAULT 0,
    hook_score integer DEFAULT 0,
    engagement_score integer DEFAULT 0,
    value_score integer DEFAULT 0,
    shareability_score integer DEFAULT 0,
    hook_type character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    text_translation text,
    title_zh character varying(120),
    golden_quote_zh character varying(200)
);

CREATE TABLE public.processing_cache (
    cache_key character varying(255) NOT NULL,
    source_url text NOT NULL,
    source_type character varying(20) NOT NULL,
    video_path text,
    transcript_text text,
    analysis_json text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.schema_migrations (
    version character varying(255) NOT NULL,
    applied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.session (
    id text NOT NULL,
    "expiresAt" timestamp(3) without time zone NOT NULL,
    token text NOT NULL,
    "createdAt" timestamp(3) without time zone NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL,
    "ipAddress" text,
    "userAgent" text,
    "userId" text NOT NULL
);

CREATE TABLE public.account (
    id text NOT NULL,
    "accountId" text NOT NULL,
    "providerId" text NOT NULL,
    "userId" text NOT NULL,
    "accessToken" text,
    "refreshToken" text,
    "idToken" text,
    "accessTokenExpiresAt" timestamp(3) without time zone,
    "refreshTokenExpiresAt" timestamp(3) without time zone,
    scope text,
    password text,
    "createdAt" timestamp(3) without time zone NOT NULL,
    "updatedAt" timestamp(3) without time zone NOT NULL
);

CREATE TABLE public.verification (
    id text NOT NULL,
    identifier text NOT NULL,
    value text NOT NULL,
    "expiresAt" timestamp(3) without time zone NOT NULL,
    "createdAt" timestamp(3) without time zone,
    "updatedAt" timestamp(3) without time zone
);

CREATE TABLE public.stripe_webhook_events (
    id text NOT NULL,
    type text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Primary keys
ALTER TABLE ONLY public._prisma_migrations
    ADD CONSTRAINT _prisma_migrations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.generated_clips
    ADD CONSTRAINT generated_clips_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.processing_cache
    ADD CONSTRAINT processing_cache_pkey PRIMARY KEY (cache_key);

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);

ALTER TABLE ONLY public.session
    ADD CONSTRAINT session_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.account
    ADD CONSTRAINT account_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.verification
    ADD CONSTRAINT verification_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.stripe_webhook_events
    ADD CONSTRAINT stripe_webhook_events_pkey PRIMARY KEY (id);

-- Indexes
CREATE INDEX idx_generated_clips_clip_order ON public.generated_clips USING btree (clip_order);
CREATE INDEX idx_generated_clips_created_at ON public.generated_clips USING btree (created_at);
CREATE INDEX idx_generated_clips_task_id ON public.generated_clips USING btree (task_id);
CREATE INDEX idx_processing_cache_source_url ON public.processing_cache USING btree (source_url);
CREATE UNIQUE INDEX session_token_key ON public.session USING btree (token);
CREATE INDEX sources_created_at_idx ON public.sources USING btree (created_at);
CREATE INDEX tasks_created_at_idx ON public.tasks USING btree (created_at);
CREATE INDEX tasks_source_id_idx ON public.tasks USING btree (source_id);
CREATE INDEX tasks_status_idx ON public.tasks USING btree (status);
CREATE INDEX tasks_user_id_idx ON public.tasks USING btree (user_id);
CREATE UNIQUE INDEX users_email_key ON public.users USING btree (email);
CREATE UNIQUE INDEX users_stripe_customer_id_key ON public.users USING btree (stripe_customer_id);
CREATE UNIQUE INDEX users_stripe_subscription_id_key ON public.users USING btree (stripe_subscription_id);

-- Foreign keys (after all tables exist)
ALTER TABLE ONLY public.account
    ADD CONSTRAINT "account_userId_fkey" FOREIGN KEY ("userId") REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE ONLY public.session
    ADD CONSTRAINT "session_userId_fkey" FOREIGN KEY ("userId") REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id) ON UPDATE CASCADE ON DELETE SET NULL;

ALTER TABLE ONLY public.generated_clips
    ADD CONSTRAINT generated_clips_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE;

-- Triggers: Prisma updates "updatedAt" in app; only generated_clips uses DB-side updated_at refresh
CREATE TRIGGER update_generated_clips_updated_at
    BEFORE UPDATE ON public.generated_clips
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
