"""Localizador rápido de UBS próximas usando a base pública de UBS do CNES.

Estratégia:
- Baixa o arquivo público compactado do Ministério da Saúde quando não há base local.
- Constrói um banco SQLite local com índice nas coordenadas.
- Nas buscas seguintes, consulta apenas uma região ao redor da pessoa, sem baixar
  nem percorrer novamente todas as UBS do Brasil.
- Atualiza a base em segundo plano quando o cache vence, usando os dados antigos
  enquanto a atualização é feita.

IMPORTANTE: retorna UBS geograficamente próximas; não confirma a UBS de cadastro
individual nem a área de abrangência oficial de cada unidade.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import sqlite3
import threading
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests

# Fonte pública oficial do dataset de UBS cadastradas no CNES.
DATASET_ZIP_URL = (
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/"
    "Unidades_Basicas_Saude-UBS_json.zip"
)
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

DB_PATH = Path(os.getenv("CNES_UBS_DB", "cnes_ubs.sqlite3"))
# Compatibilidade opcional com a versão anterior, que guardava JSON completo.
LEGACY_CACHE_PATH = Path(os.getenv("CNES_UBS_CACHE", "cnes_ubs_cache.json"))
CACHE_TTL_SECONDS = 24 * 60 * 60
HTTP_TIMEOUT_SECONDS = 45
USER_AGENT = "CalorAvisoUBSFinder/2.0 (public-health-service-locator)"
INITIAL_RADIUS_KM = 8.0
MAX_RADIUS_KM = 20000.0

_nominatim_lock = threading.Lock()
_nominatim_last_request = 0.0
_db_lock = threading.Lock()
_refresh_thread_lock = threading.Lock()
_refresh_thread: threading.Thread | None = None


class UBSLookupError(RuntimeError):
    """Erro recuperável ao buscar coordenadas ou unidades públicas."""


def _normalizar_chave(value: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def _numero(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numero = float(value)
        return numero if math.isfinite(numero) else None
    texto = str(value).strip().replace(",", ".")
    if not texto:
        return None
    try:
        numero = float(texto)
        return numero if math.isfinite(numero) else None
    except ValueError:
        return None


def _extrair_registros(payload: Any) -> list[dict[str, Any]]:
    """Aceita listas JSON e wrappers comuns (data, results, records etc.)."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    nomes = (
        "data", "dados", "results", "resultados", "items", "itens", "content",
        "records", "ubs", "unidades", "unidades_basicas_de_saude",
    )
    mapa = {_normalizar_chave(k): v for k, v in payload.items()}
    for nome in nomes:
        valor = mapa.get(_normalizar_chave(nome))
        if isinstance(valor, list):
            return [item for item in valor if isinstance(item, dict)]
        if isinstance(valor, dict):
            registros = _extrair_registros(valor)
            if registros:
                return registros
    for valor in payload.values():
        if isinstance(valor, list) and valor and all(isinstance(item, dict) for item in valor):
            return valor
    return []


def _valor(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    mapa = {_normalizar_chave(chave): valor for chave, valor in row.items()}
    for alias in aliases:
        chave = _normalizar_chave(alias)
        if chave in mapa and mapa[chave] not in (None, ""):
            return mapa[chave]
    for valor in row.values():
        if isinstance(valor, dict):
            encontrado = _valor(valor, aliases)
            if encontrado not in (None, ""):
                return encontrado
    return None


def _formatar_ubs(row: dict[str, Any]) -> dict[str, Any] | None:
    latitude = _numero(_valor(row, (
        "latitude", "nu_latitude", "vl_latitude", "co_latitude", "lat", "latitud",
    )))
    longitude = _numero(_valor(row, (
        "longitude", "nu_longitude", "vl_longitude", "co_longitude", "lon", "long", "lng",
    )))
    if (
        latitude is None or longitude is None
        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
        or (latitude == 0 and longitude == 0)
    ):
        return None

    nome = _valor(row, (
        "no_fantasia", "nome_fantasia", "nome_ubs", "nome_estabelecimento",
        "nome", "estabelecimento", "no_estab", "nome_unidade",
    ))
    logradouro = _valor(row, (
        "ds_endereco", "endereco", "no_logradouro", "logradouro", "ds_logradouro",
        "nome_logradouro",
    ))
    numero = _valor(row, ("nu_endereco", "numero", "num_endereco"))
    bairro = _valor(row, ("no_bairro", "bairro", "ds_bairro"))
    municipio = _valor(row, ("no_municipio", "municipio", "nome_municipio", "localidade", "no_cidade"))
    uf = _valor(row, ("sg_uf", "uf", "estado"))
    cep = _valor(row, ("co_cep", "cep", "nu_cep"))
    cnes = _valor(row, ("co_cnes", "cnes", "codigo_cnes", "cod_cnes"))

    partes: list[str] = []
    if logradouro:
        parte = str(logradouro).strip()
        if numero and str(numero).strip() not in ("0", "S/N", "s/n"):
            parte += f", {str(numero).strip()}"
        partes.append(parte)
    elif numero:
        partes.append(str(numero).strip())
    if bairro:
        partes.append(str(bairro).strip())
    cidade_uf = "/".join(str(p).strip() for p in (municipio, uf) if p)
    if cidade_uf:
        partes.append(cidade_uf)
    if cep:
        cep_fmt = re.sub(r"\D", "", str(cep))
        partes.append(f"CEP {cep_fmt}" if cep_fmt else f"CEP {cep}")

    return {
        "nome": str(nome or "Unidade Básica de Saúde").strip(),
        "endereco": ", ".join(partes) if partes else "Endereço não informado na base pública",
        "latitude": latitude,
        "longitude": longitude,
        "cnes": str(cnes).strip() if cnes else None,
    }


def _ler_json_do_zip(conteudo_zip: bytes) -> list[dict[str, Any]]:
    """Lê o(s) arquivo(s) JSON do ZIP oficial, tolerando JSON e JSONL."""
    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    except zipfile.BadZipFile as erro:
        raise UBSLookupError("O arquivo público de UBS baixado não é um ZIP válido.") from erro

    todos: list[dict[str, Any]] = []
    with arquivo_zip:
        nomes = [n for n in arquivo_zip.namelist() if not n.endswith("/")]
        nomes_json = [n for n in nomes if n.lower().endswith((".json", ".jsonl", ".ndjson"))]
        if not nomes_json:
            raise UBSLookupError("O arquivo público baixado não contém arquivos JSON reconhecíveis.")

        for nome in nomes_json:
            bruto = arquivo_zip.read(nome)
            try:
                texto = bruto.decode("utf-8-sig")
            except UnicodeDecodeError:
                texto = bruto.decode("latin-1")
            try:
                payload = json.loads(texto)
                registros = _extrair_registros(payload)
            except json.JSONDecodeError:
                # JSON Lines: um objeto JSON por linha.
                registros = []
                for linha in texto.splitlines():
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        item = json.loads(linha)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        registros.append(item)
            if registros:
                todos.extend(registros)

    if not todos:
        raise UBSLookupError("O arquivo público de UBS não trouxe registros em um formato reconhecido.")
    return todos


def _timestamp_db() -> float | None:
    if not DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as con:
            row = con.execute("SELECT value FROM metadata WHERE key='updated_at'").fetchone()
            return float(row[0]) if row else None
    except sqlite3.Error:
        return None


def _db_pronta() -> bool:
    try:
        with sqlite3.connect(DB_PATH, timeout=3) as con:
            existe = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ubs'"
            ).fetchone()
            if not existe:
                return False
            n = con.execute("SELECT COUNT(*) FROM ubs").fetchone()[0]
            return n > 0
    except sqlite3.Error:
        return False


def _montar_banco(registros: Iterable[dict[str, Any]]) -> int:
    """Cria um banco temporário e o troca pelo atual para evitar cache parcial."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporario = DB_PATH.with_suffix(DB_PATH.suffix + ".tmp")
    try:
        temporario.unlink(missing_ok=True)
    except OSError:
        pass

    inseridos = 0
    try:
        with sqlite3.connect(temporario, timeout=30) as con:
            con.execute("PRAGMA journal_mode=OFF")
            con.execute("PRAGMA synchronous=OFF")
            con.execute("PRAGMA temp_store=MEMORY")
            con.execute("""
                CREATE TABLE ubs (
                    id INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL,
                    endereco TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    cnes TEXT
                )
            """)
            con.execute("CREATE INDEX idx_ubs_lat_lon ON ubs(latitude, longitude)")
            con.execute("CREATE INDEX idx_ubs_cnes ON ubs(cnes)")
            con.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

            lote: list[tuple[str, str, float, float, str | None]] = []
            for registro in registros:
                unidade = _formatar_ubs(registro)
                if unidade is None:
                    continue
                lote.append((
                    unidade["nome"], unidade["endereco"], unidade["latitude"],
                    unidade["longitude"], unidade["cnes"],
                ))
                if len(lote) >= 2000:
                    con.executemany(
                        "INSERT INTO ubs(nome, endereco, latitude, longitude, cnes) VALUES (?, ?, ?, ?, ?)",
                        lote,
                    )
                    inseridos += len(lote)
                    lote.clear()
            if lote:
                con.executemany(
                    "INSERT INTO ubs(nome, endereco, latitude, longitude, cnes) VALUES (?, ?, ?, ?, ?)",
                    lote,
                )
                inseridos += len(lote)
            if inseridos == 0:
                raise UBSLookupError(
                    "A base pública foi baixada, mas não encontrei coordenadas utilizáveis nos registros."
                )
            con.execute("INSERT INTO metadata(key, value) VALUES ('updated_at', ?)", (str(time.time()),))
            con.execute("INSERT INTO metadata(key, value) VALUES ('source', ?)", (DATASET_ZIP_URL,))
            con.commit()

        # O banco temporário foi fechado; substituir atomicamente quando possível.
        temporario.replace(DB_PATH)
        return inseridos
    except Exception:
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _baixar_e_preparar() -> int:
    """Baixa o arquivo oficial e indexa localmente. Chamada na primeira execução/atualização."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/zip, application/octet-stream, */*"})
    try:
        resposta = session.get(DATASET_ZIP_URL, timeout=HTTP_TIMEOUT_SECONDS, stream=True)
        resposta.raise_for_status()
        partes: list[bytes] = []
        total = 0
        limite_bytes = int(os.getenv("CNES_UBS_MAX_DOWNLOAD_MB", "600")) * 1024 * 1024
        for parte in resposta.iter_content(chunk_size=1024 * 1024):
            if not parte:
                continue
            total += len(parte)
            if total > limite_bytes:
                raise UBSLookupError(
                    f"O arquivo de UBS excede o limite local de {limite_bytes // (1024 * 1024)} MB."
                )
            partes.append(parte)
        conteudo = b"".join(partes)
    except UBSLookupError:
        raise
    except requests.RequestException as erro:
        raise UBSLookupError(
            "Não consegui baixar a base pública de UBS agora. Tente novamente quando houver conexão."
        ) from erro

    registros = _ler_json_do_zip(conteudo)
    return _montar_banco(registros)


def _tentar_cache_legado() -> bool:
    """Migra um cache JSON criado pela versão anterior, se estiver disponível e válido."""
    try:
        if not LEGACY_CACHE_PATH.exists():
            return False
        if time.time() - LEGACY_CACHE_PATH.stat().st_mtime > CACHE_TTL_SECONDS:
            return False
        payload = json.loads(LEGACY_CACHE_PATH.read_text(encoding="utf-8"))
        registros = _extrair_registros(payload)
        if not registros:
            return False
        _montar_banco(registros)
        return True
    except (OSError, json.JSONDecodeError, sqlite3.Error, UBSLookupError):
        return False


def _atualizar_em_segundo_plano() -> None:
    global _refresh_thread
    with _refresh_thread_lock:
        if _refresh_thread is not None and _refresh_thread.is_alive():
            return

        def trabalho() -> None:
            try:
                with _db_lock:
                    _baixar_e_preparar()
            except Exception:
                # Se existe uma base antiga válida, ela continua disponível.
                pass

        _refresh_thread = threading.Thread(target=trabalho, name="cnes-ubs-refresh", daemon=True)
        _refresh_thread.start()


def preparar_cache_ubs(forcar_atualizacao: bool = False) -> int:
    """Prepara a base local. Execute uma vez antes de iniciar o bot para primeira busca rápida."""
    with _db_lock:
        timestamp = _timestamp_db()
        if not forcar_atualizacao and _db_pronta() and timestamp is not None:
            if time.time() - timestamp <= CACHE_TTL_SECONDS:
                with sqlite3.connect(DB_PATH) as con:
                    return int(con.execute("SELECT COUNT(*) FROM ubs").fetchone()[0])
        if not _db_pronta() and _tentar_cache_legado():
            with sqlite3.connect(DB_PATH) as con:
                return int(con.execute("SELECT COUNT(*) FROM ubs").fetchone()[0])
        return _baixar_e_preparar()


def _garantir_base_pronta() -> None:
    timestamp = _timestamp_db()
    pronta = _db_pronta()
    if not pronta:
        # Se o carregamento em background iniciado na importação já está em andamento,
        # espere por ele em vez de disparar uma segunda transferência concorrente.
        with _refresh_thread_lock:
            thread_inicial = _refresh_thread
        if thread_inicial is not None and thread_inicial.is_alive():
            thread_inicial.join()
            timestamp = _timestamp_db()
            pronta = _db_pronta()
    if pronta:
        # Base local já existente: responde com ela imediatamente, atualizando em background se vencida.
        if timestamp is None or time.time() - timestamp > CACHE_TTL_SECONDS:
            _atualizar_em_segundo_plano()
        return

    # A primeira utilização não tem cache: uma preparação síncrona é inevitável.
    with _db_lock:
        if _db_pronta():
            return
        if _tentar_cache_legado():
            return
        _baixar_e_preparar()


def carregar_ubs() -> list[dict[str, Any]]:
    """Compatibilidade com o módulo anterior; prefere usar buscar_ubs_proximas()."""
    _garantir_base_pronta()
    with sqlite3.connect(DB_PATH, timeout=15) as con:
        con.row_factory = sqlite3.Row
        linhas = con.execute(
            "SELECT nome, endereco, latitude, longitude, cnes FROM ubs"
        ).fetchall()
    return [dict(linha) for linha in linhas]


def _distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    raio = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * raio * math.asin(min(1.0, math.sqrt(a)))


def _buscar_por_raio(
    con: sqlite3.Connection, latitude: float, longitude: float, raio_km: float,
) -> list[dict[str, Any]]:
    # Caixa delimitadora: em latitude, ~111 km por grau; longitude ajustada pela latitude.
    delta_lat = raio_km / 110.574
    cos_lat = max(0.01, abs(math.cos(math.radians(latitude))))
    delta_lon = min(180.0, raio_km / (111.320 * cos_lat))
    min_lat, max_lat = max(-90.0, latitude - delta_lat), min(90.0, latitude + delta_lat)
    min_lon, max_lon = longitude - delta_lon, longitude + delta_lon

    if min_lon < -180 or max_lon > 180:
        # Cruzamento do antimeridiano (não esperado no Brasil, mas deixa a função geral).
        if min_lon < -180:
            cond_lon = "(longitude >= ? OR longitude <= ?)"
            params_lon: tuple[float, float] = (min_lon + 360, max_lon)
        else:
            cond_lon = "(longitude >= ? OR longitude <= ?)"
            params_lon = (min_lon, max_lon - 360)
    else:
        cond_lon = "longitude BETWEEN ? AND ?"
        params_lon = (min_lon, max_lon)

    consulta = f"""
        SELECT nome, endereco, latitude, longitude, cnes
        FROM ubs
        WHERE latitude BETWEEN ? AND ? AND {cond_lon}
    """
    linhas = con.execute(consulta, (min_lat, max_lat, *params_lon)).fetchall()
    itens = []
    for linha in linhas:
        distancia = _distancia_km(latitude, longitude, float(linha["latitude"]), float(linha["longitude"]))
        item = dict(linha)
        item["distancia_km"] = distancia
        itens.append(item)
    itens.sort(key=lambda item: item["distancia_km"])
    return itens


def buscar_ubs_proximas(latitude: float, longitude: float, quantidade: int = 3) -> list[dict[str, Any]]:
    """Retorna as UBS próximas por distância em linha reta, usando busca espacial indexada."""
    latitude, longitude = float(latitude), float(longitude)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise UBSLookupError("As coordenadas informadas são inválidas.")

    quantidade = max(1, min(int(quantidade), 5))
    _garantir_base_pronta()

    try:
        with sqlite3.connect(DB_PATH, timeout=20) as con:
            con.row_factory = sqlite3.Row
            raio = INITIAL_RADIUS_KM
            while True:
                candidatos = _buscar_por_raio(con, latitude, longitude, raio)
                # Só encerramos quando a unidade de posição N está dentro da borda do raio;
                # assim, locais fora da caixa não podem ser mais próximos do que o N-ésimo.
                if len(candidatos) >= quantidade and candidatos[quantidade - 1]["distancia_km"] <= raio:
                    return candidatos[:quantidade]
                if raio >= MAX_RADIUS_KM:
                    if candidatos:
                        return candidatos[:quantidade]
                    raise UBSLookupError("Não encontrei UBS com coordenadas utilizáveis na base pública.")
                raio = min(raio * 2, MAX_RADIUS_KM)
    except sqlite3.Error as erro:
        raise UBSLookupError("Não consegui consultar o índice local de UBS.") from erro


def coordenadas_por_cep(cep: str) -> tuple[float, float, str]:
    """Geocodifica a área do CEP; o nome e o endereço residencial não são enviados."""
    cep_limpo = re.sub(r"\D", "", cep)
    if not re.fullmatch(r"\d{8}", cep_limpo):
        raise UBSLookupError("CEP inválido. Digite os 8 números do CEP.")

    try:
        resposta = requests.get(
            VIACEP_URL.format(cep=cep_limpo), timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        resposta.raise_for_status()
        dados_cep = resposta.json()
    except (requests.RequestException, ValueError) as erro:
        raise UBSLookupError(
            "Não consegui consultar esse CEP agora. Tente novamente ou compartilhe a localização."
        ) from erro

    if dados_cep.get("erro"):
        raise UBSLookupError("Esse CEP não foi encontrado. Confira os números ou compartilhe a localização.")

    municipio, uf = dados_cep.get("localidade"), dados_cep.get("uf")
    if not municipio or not uf:
        raise UBSLookupError("Não consegui identificar o município desse CEP.")

    global _nominatim_last_request
    with _nominatim_lock:
        espera = 1.05 - (time.monotonic() - _nominatim_last_request)
        if espera > 0:
            time.sleep(espera)
        try:
            geor = requests.get(
                NOMINATIM_URL,
                params={
                    "postalcode": cep_limpo,
                    "city": municipio,
                    "state": uf,
                    "country": "Brasil",
                    "countrycodes": "br",
                    "format": "jsonv2",
                    "limit": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            _nominatim_last_request = time.monotonic()
            geor.raise_for_status()
            resultados = geor.json()
        except (requests.RequestException, ValueError) as erro:
            raise UBSLookupError(
                "Não consegui transformar o CEP em uma localização aproximada. Tente compartilhar o GPS."
            ) from erro

    if not resultados:
        raise UBSLookupError("Não consegui estimar a localização desse CEP. Tente compartilhar o GPS.")
    lat = _numero(resultados[0].get("lat"))
    lon = _numero(resultados[0].get("lon"))
    if lat is None or lon is None:
        raise UBSLookupError("O serviço de localização não retornou coordenadas válidas para esse CEP.")
    return lat, lon, f"área aproximada do CEP {cep_limpo} — {municipio}/{uf}"


def buscar_ubs_por_cep(cep: str, quantidade: int = 3) -> tuple[str, list[dict[str, Any]]]:
    lat, lon, descricao = coordenadas_por_cep(cep)
    return descricao, buscar_ubs_proximas(lat, lon, quantidade)


def iniciar_precarregamento() -> None:
    """Inicia a preparação em background se ainda não existe uma base local."""
    if _db_pronta():
        if (_timestamp_db() or 0) + CACHE_TTL_SECONDS < time.time():
            _atualizar_em_segundo_plano()
        return
    _atualizar_em_segundo_plano()


# Começa a preparar a base enquanto o bot sobe e a pessoa responde ao cadastro.
# A primeira busca pode esperar o carregamento se a base ainda não estiver pronta.
if __name__ != "__main__" and os.getenv("CNES_UBS_AUTO_PRELOAD", "1") != "0":
    iniciar_precarregamento()


if __name__ == "__main__":
    # Rode uma vez antes de iniciar o bot. Depois disso, as buscas são locais e rápidas.
    import argparse
    parser = argparse.ArgumentParser(description="Preparar/atualizar o cache local de UBS do CNES")
    parser.add_argument("--force", action="store_true", help="baixar novamente mesmo se o cache estiver válido")
    args = parser.parse_args()
    try:
        total = preparar_cache_ubs(forcar_atualizacao=args.force)
        print(f"Base local preparada: {total:,} UBS com coordenadas válidas.")
        print(f"Arquivo local: {DB_PATH.resolve()}")
        print("As próximas buscas serão feitas no SQLite local, sem baixar a lista nacional novamente.")
    except UBSLookupError as erro:
        raise SystemExit(f"Não foi possível preparar a base de UBS: {erro}")
