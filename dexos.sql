

CREATE DATABASE IF NOT EXISTS dexos_db;
USE dexos_db;

CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    ultimo_login DATETIME,
    nivel_acesso ENUM('admin', 'usuario', 'convidado') DEFAULT 'usuario',
    ativo BOOLEAN DEFAULT TRUE,
    foto_perfil VARCHAR(255),
);

CREATE TABLE dispositivos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    tipo ENUM('computador', 'smartphone', 'tablet', 'robo', 'iot') NOT NULL,
    endereco_mac VARCHAR(17) UNIQUE,
    endereco_ip VARCHAR(45),
    data_conexao DATETIME DEFAULT CURRENT_TIMESTAMP,
    ultima_atividade DATETIME,
    usuario_id INT,
    ativo BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE rostos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    nome VARCHAR(100) NOT NULL,
    encoding_facial TEXT NOT NULL,
    caminho_imagem VARCHAR(255),
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    precisao_treinamento FLOAT,
    ativo BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);


CREATE TABLE log_reconhecimentos_faciais (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rosto_id INT,
    dispositivo_id INT,
    data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    confianca FLOAT,
    coordenadas TEXT,
    caminho_imagem VARCHAR(255),
    FOREIGN KEY (rosto_id) REFERENCES rostos(id) ON DELETE SET NULL,
    FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id) ON DELETE SET NULL
);

CREATE TABLE objetos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    categoria VARCHAR(50),
    caminho_imagem_treinamento VARCHAR(255),
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    ativo BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA: Log de Reconhecimento de Objetos
-- =====================================================
CREATE TABLE log_reconhecimento_objetos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    objeto_id INT,
    dispositivo_id INT,
    data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    confianca FLOAT,
    coordenadas TEXT,
    caminho_imagem VARCHAR(255),
    FOREIGN KEY (objeto_id) REFERENCES objetos(id) ON DELETE SET NULL,
    FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id) ON DELETE SET NULL
);

-- =====================================================
-- TABELA: Comandos de Voz
-- =====================================================
CREATE TABLE comandos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    comando VARCHAR(255) NOT NULL,
    acao TEXT NOT NULL,
    categoria VARCHAR(50),
    descricao TEXT,
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    ativo BOOLEAN DEFAULT TRUE,
    precisa_privilegio BOOLEAN DEFAULT FALSE
);

-- =====================================================
-- TABELA: Log de Comandos
-- =====================================================
CREATE TABLE log_comandos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    comando_id INT,
    usuario_id INT,
    dispositivo_id INT,
    data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    comando_reconhecido TEXT,
    acao_executada TEXT,
    sucesso BOOLEAN DEFAULT TRUE,
    tempo_resposta FLOAT,
    FOREIGN KEY (comando_id) REFERENCES comandos(id) ON DELETE SET NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id) ON DELETE SET NULL
);

-- =====================================================
-- TABELA: Configurações do Sistema
-- =====================================================
CREATE TABLE configuracoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    chave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT,
    tipo VARCHAR(50),
    descricao TEXT,
    categoria VARCHAR(50) DEFAULT 'geral',
    editavel BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA: Dispositivos Robótica
-- =====================================================
CREATE TABLE dispositivos_robotica (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(50),
    endereco_ip VARCHAR(45),
    porta INT,
    protocolo VARCHAR(20),
    data_conexao DATETIME DEFAULT CURRENT_TIMESTAMP,
    ultima_comunicacao DATETIME,
    status ENUM('online', 'offline', 'ocupado', 'erro') DEFAULT 'offline',
    comandos_suportados JSON,
    configuracao JSON
);

-- =====================================================
-- TABELA: Log de Comandos Robótica
-- =====================================================
CREATE TABLE log_comandos_robotica (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispositivo_id INT,
    comando VARCHAR(100) NOT NULL,
    parametros TEXT,
    data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    sucesso BOOLEAN DEFAULT TRUE,
    resposta TEXT,
    tempo_resposta FLOAT,
    FOREIGN KEY (dispositivo_id) REFERENCES dispositivos_robotica(id) ON DELETE CASCADE
);

-- =====================================================
-- TABELA: Agendamentos
-- =====================================================
CREATE TABLE agendamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT,
    titulo VARCHAR(255) NOT NULL,
    descricao TEXT,
    data_hora DATETIME NOT NULL,
    repeticao ENUM('nenhuma', 'diaria', 'semanal', 'mensal') DEFAULT 'nenhuma',
    comando_executar TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

-- =====================================================
-- TABELA: Log do Sistema
-- =====================================================
CREATE TABLE log_sistema (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nivel ENUM('info', 'aviso', 'erro', 'critico') DEFAULT 'info',
    modulo VARCHAR(100),
    mensagem TEXT,
    data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    usuario_id INT,
    dispositivo_id INT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id) ON DELETE SET NULL
);

-- =====================================================
-- ÍNDICES
-- =====================================================
CREATE INDEX idx_log_comandos_data ON log_comandos(data_hora);
CREATE INDEX idx_log_comandos_usuario ON log_comandos(usuario_id);
CREATE INDEX idx_log_recon_facial_data ON log_reconhecimentos_faciais(data_hora);
CREATE INDEX idx_log_recon_objetos_data ON log_reconhecimento_objetos(data_hora);
CREATE INDEX idx_usuarios_email ON usuarios(email);
CREATE INDEX idx_dispositivos_mac ON dispositivos(endereco_mac);
