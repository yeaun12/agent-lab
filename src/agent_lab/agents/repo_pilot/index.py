"""3.3 임베딩과 Qdrant 색인: 청크를 벡터로 바꿔 저장하고, 질문과 가까운 청크를 찾는다."""

import atexit
import json
import time
import uuid

import httpx
from qdrant_client import QdrantClient, models

from agent_lab.agents.repo_pilot.chunking import Chunk, chunk_file
from agent_lab.agents.repo_pilot.ingest import PROJECT, REPOS_DIR, collect

OLLAMA = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
DIM = 768  # 1.3에서 확인한 nomic-embed-text 벡터 차원
BATCH = 32
QDRANT_PATH = PROJECT / "data" / "qdrant"  # 로컬 모드: 서버 없이 이 폴더에 파일로 저장
MANIFEST_DIR = PROJECT / "data" / "index"  # 컬렉션별로 '어느 파일을 어떤 해시로 색인했나' 기록

# nomic-embed-text는 저장할 글과 질문에 서로 다른 접두어를 붙이도록 학습됐다
PREFIX = {"document": "search_document: ", "query": "search_query: "}

_client: QdrantClient | None = None


def qdrant() -> QdrantClient:
    """Qdrant 클라이언트를 하나만 만들어 재사용한다.
    로컬 모드는 한 번에 한 프로그램만 폴더를 열 수 있다 (다른 창에서 열려 있으면 오류)."""
    global _client
    if _client is None:
        _client = QdrantClient(path=str(QDRANT_PATH))
        # 프로그램이 끝나기 직전에 닫는다. 안 닫으면 종료 중에 'Exception ignored ... shutting down' 경고가 찍힌다
        atexit.register(_client.close)
    return _client


def collection_name(repo: str, strategy: str, prefix: bool) -> str:
    """예: httpx_B_p (p = 접두어 사용)"""
    return f"{repo}_{strategy}" + ("_p" if prefix else "")


def embed(texts: list[str], kind: str = "document", prefix: bool = True) -> list[list[float]]:
    """Ollama로 글 목록을 벡터 목록으로 바꾼다. BATCH개씩 나눠 보낸다."""
    vectors = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        if prefix:
            batch = [PREFIX[kind] + t for t in batch]
        r = httpx.post(OLLAMA, json={"model": EMBED_MODEL, "input": batch}, timeout=600)
        r.raise_for_status()
        vectors += r.json()["embeddings"]
    return vectors


def point_id(chunk: Chunk) -> str:
    """Qdrant 포인트 ID는 UUID여야 한다. 청크 ID(32자리 16진수)를 그대로 UUID로 쓴다."""
    return str(uuid.UUID(hex=chunk.id))


def dirs_of(path: str) -> list[str]:
    """'httpx/_transports/default.py' → ['httpx', 'httpx/_transports'] (폴더 필터용)"""
    parts = path.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def build_index(repo: str, strategy: str, prefix: bool = True) -> dict:
    """증분 색인. 해시가 바뀐 파일만 다시 임베딩하고, 사라진 파일의 포인트는 지운다."""
    root = REPOS_DIR / repo
    name = collection_name(repo, strategy, prefix)
    db = qdrant()
    if not db.collection_exists(name):
        db.create_collection(name, vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE))
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = MANIFEST_DIR / f"{name}.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    records, _ = collect(root)
    now = {r.path: r.sha256 for r in records}
    changed = [r for r in records if old.get(r.path) != r.sha256]  # 새 파일 + 내용이 바뀐 파일
    removed = [p for p in old if p not in now]

    # 바뀐 파일과 사라진 파일의 옛 포인트를 먼저 지운다 (청크 경계가 달라졌을 수 있다)
    for path in [r.path for r in changed if r.path in old] + removed:
        db.delete(name, points_selector=models.FilterSelector(
            filter=models.Filter(must=[models.FieldCondition(key="path", match=models.MatchValue(value=path))])
        ))

    chunks = [c for r in changed for c in chunk_file(r, root, strategy)]
    start = time.perf_counter()
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        vectors = embed([c.text for c in batch], "document", prefix)
        db.upsert(name, points=[
            models.PointStruct(id=point_id(c), vector=v, payload={**c.model_dump(), "dirs": dirs_of(c.path)})
            for c, v in zip(batch, vectors)
        ])
        done = i + len(batch)
        print(f"\r  임베딩 {done}/{len(chunks)}", end="", flush=True)
    seconds = time.perf_counter() - start
    if chunks:
        print()
    manifest_path.write_text(json.dumps(now, indent=0), encoding="utf-8")  # 다 끝난 뒤에 기록
    return {
        "collection": name,
        "files": len(records),
        "changed_files": len(changed),
        "skipped_files": len(records) - len(changed),
        "removed_files": len(removed),
        "chunks_embedded": len(chunks),
        "seconds": round(seconds, 1),
        "chunks_per_sec": round(len(chunks) / seconds, 2) if chunks else None,
        "points": db.count(name).count,
    }


def search(query: str, collection: str, k: int = 5, folder: str | None = None, kind: str | None = None) -> list[dict]:
    """질문과 가까운 청크 k개. folder='httpx/_transports'처럼 폴더로, kind='function'처럼 종류로 거를 수 있다."""
    prefix = not collection.endswith(("_A", "_B"))  # 접두어로 만든 컬렉션이면 질문에도 붙인다
    vector = embed([query], "query", prefix)[0]
    must = []
    if folder:
        must.append(models.FieldCondition(key="dirs", match=models.MatchValue(value=folder)))
    if kind:
        must.append(models.FieldCondition(key="kind", match=models.MatchValue(value=kind)))
    hits = qdrant().query_points(collection, query=vector, limit=k, query_filter=models.Filter(must=must) if must else None)
    return [{"score": round(h.score, 3), **h.payload} for h in hits.points]