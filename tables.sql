


CREATE TABLE documentos_similitud (
    id SERIAL PRIMARY KEY,
    moodle_submission_id BIGINT UNIQUE,
	course_id BIGINT NOT NULL,
	cmid BIGINT NOT NULL,
    assign_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    timecreated TIMESTAMP,
    timemodified TIMESTAMP,
    filename TEXT,
    fileurl TEXT,
    texto TEXT NOT NULL,
    texto_limpio TEXT NOT NULL,
    fecha_registro TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_documentos_assign_id ON documentos_similitud(assign_id);
CREATE INDEX idx_documentos_user_id ON documentos_similitud(user_id);



CREATE TABLE IF NOT EXISTS resultados_similitud (
    id SERIAL PRIMARY KEY,
	course_id BIGINT NOT NULL,
	cmid BIGINT NOT NULL,
    assign_id_similitud BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    moodle_submission_id BIGINT NOT NULL,
    url TEXT,
    archivo TEXT,
    user_id_similitud BIGINT NOT NULL,
    moodle_submission_id_similitud BIGINT NOT NULL,
    url_similitud TEXT,
    archivo_similitud TEXT,
    score_similitud NUMERIC(10,6) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resultados_assign_id_similitud
    ON resultados_similitud(assign_id_similitud);

CREATE INDEX IF NOT EXISTS idx_resultados_user_id
    ON resultados_similitud(user_id);

CREATE INDEX IF NOT EXISTS idx_resultados_user_id_similitud
    ON resultados_similitud(user_id_similitud);

CREATE INDEX IF NOT EXISTS idx_resultados_submission_id
    ON resultados_similitud(moodle_submission_id);

CREATE INDEX IF NOT EXISTS idx_resultados_submission_id_similitud
    ON resultados_similitud(moodle_submission_id_similitud);
