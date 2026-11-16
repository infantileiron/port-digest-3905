-- 清退批次：到期明细按上海计划日清退，保留无班次身份统计。
-- 参考DDL（无在线迁移执行器）；ORM create_all 与 backend 启动时的幂等 ALTER 已覆盖同等变更。

ALTER TABLE public.arrivals ADD COLUMN IF NOT EXISTS planned_day character varying(10);
ALTER TABLE public.arrivals ADD COLUMN IF NOT EXISTS delay_minutes double precision;
ALTER TABLE public.arrivals ADD COLUMN IF NOT EXISTS purged boolean DEFAULT false;
ALTER TABLE public.receipts ADD COLUMN IF NOT EXISTS purged boolean DEFAULT false;

CREATE TABLE IF NOT EXISTS public.purge_batches (
    id integer NOT NULL,
    cutoff_day character varying(10) NOT NULL,
    state character varying(20),
    created_by character varying(100),
    created_at character varying(40),
    started_at character varying(40),
    finished_at character varying(40)
);

CREATE SEQUENCE IF NOT EXISTS public.purge_batches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.purge_batches_id_seq OWNED BY public.purge_batches.id;

ALTER TABLE ONLY public.purge_batches ALTER COLUMN id SET DEFAULT nextval('public.purge_batches_id_seq'::regclass);

ALTER TABLE ONLY public.purge_batches
    ADD CONSTRAINT purge_batches_pkey PRIMARY KEY (id);
