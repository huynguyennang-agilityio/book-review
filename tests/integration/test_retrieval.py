"""Hybrid retrieval trên Postgres thật: 5 câu hỏi mẫu, lọc theo sách, rerank."""

import hashlib
import math
import re
from collections.abc import Callable, Iterator, Sequence

import pytest
from langchain_core.embeddings import Embeddings
from sqlalchemy import Engine

from book_review_api.config import Settings
from book_review_api.rag.index import (
    index_chunks,
    make_record_engine,
    make_record_manager,
    make_vector_engine,
    make_vector_store,
)
from book_review_api.rag.ingest import Document
from book_review_api.rag.retrieve import Chunk, retrieve

DIM = 768
BOOK = "nha-gia-kim"
OTHER = "de-men"

# (chunk_index, nội dung). Các đoạn cố ý dùng chung nhiều từ ("cậu bé", "kho báu", "sa mạc") để
# việc tìm đúng đoạn không chỉ nhờ trùng một từ.
NHA_GIA_KIM = [
    "Santiago là một cậu bé chăn cừu ở vùng Andalusia. Đêm nọ cậu mơ thấy một đứa trẻ dẫn mình "
    "tới kim tự tháp Ai Cập và nói rằng kho báu đang chờ ở đó. Giấc mơ lặp lại hai lần, khiến "
    "cậu không thể ngồi yên bên đàn cừu nữa.",
    "Câu chuyện mở đầu ở Andalusia, Tây Ban Nha, rồi đi qua cảng Tangier ở châu Phi. Từ đó đoàn "
    "lữ hành băng qua sa mạc Sahara mênh mông, nơi cát, gió và nắng quyết định mọi chuyện.",
    "Ở Tangier, một tên lừa đảo lấy sạch tiền của cậu bé. Cậu phải làm việc cho người bán pha lê "
    "suốt gần một năm để gom đủ tiền đi tiếp. Thời gian ở tiệm pha lê dạy cậu sự kiên nhẫn.",
    "Bài học xuyên suốt của cuốn sách là hãy theo đuổi huyền thoại cá nhân của mình. Khi ta thật "
    "lòng muốn một điều, cả vũ trụ sẽ hợp lại giúp ta đạt được nó; nỗi sợ thất bại mới là rào "
    "cản lớn nhất.",
    "Trong ốc đảo giữa sa mạc, Santiago gặp Fatima, cô gái đã khiến cậu biết yêu. Fatima nói "
    "rằng nếu họ thật sự thuộc về nhau thì sa mạc sẽ không ngăn cách, và nàng sẽ đợi cậu ở ốc đảo.",
    "Nhà giả kim là người thầy đưa Santiago đi qua đoạn đường khó nhất. Ông dạy cậu lắng nghe "
    "trái tim, đọc các điềm báo và hiểu ngôn ngữ của vũ trụ trước khi biến chì thành vàng.",
    "Đến chân kim tự tháp, cậu đào xuống nhưng không thấy gì; bọn cướp đánh cậu rồi tình cờ nói "
    "rằng chính chúng từng mơ thấy một kho báu giấu dưới gốc cây sung trong nhà thờ hoang ở Tây "
    "Ban Nha. Cậu hiểu ngay kho báu thật sự nằm ở đâu.",
    "Cuối truyện cậu quay về nhà thờ hoang nơi mình từng ngủ đêm, đào dưới gốc cây sung và tìm "
    "thấy rương vàng. Hành trình dài hóa ra là cách để cậu nhận ra kho báu luôn nằm ngay nơi cậu "
    "bắt đầu, và cậu trở lại gặp Fatima.",
    "Tác phẩm của Paulo Coelho được dịch ra hơn tám mươi ngôn ngữ, trở thành một trong những "
    "tiểu thuyết bán chạy nhất mọi thời đại, thường được đọc như một câu chuyện ngụ ngôn.",
]

DE_MEN = [
    "Dế Mèn là chú dế thanh niên cường tráng sống trong hang đất bên bờ ruộng. Mèn kiêu căng, "
    "hay trêu chọc người khác, và vì thế gây ra cái chết của Dế Choắt.",
    "Sau cái chết của Dế Choắt, Mèn hối hận và rút ra bài học về thói kiêu ngạo. Cậu rời hang, "
    "đi phiêu lưu qua đồng cỏ, và kết truyện là lúc Mèn trưởng thành hơn.",
    "Mèn nhìn thấy kho báu của lũ kiến trong một cái hang ở bìa sa mạc cát bên bờ ruộng, nhưng "
    "cậu chẳng thèm lấy. Nhân vật Fatima không xuất hiện trong truyện này.",
]

QUESTIONS = [
    ("hook", "Cậu bé chăn cừu mơ thấy gì khiến cậu lên đường?", 0),
    ("bối cảnh", "Câu chuyện diễn ra ở đâu, đi qua những vùng đất nào?", 1),
    ("bài học", "Bài học chính về huyền thoại cá nhân là gì?", 3),
    ("kết truyện", "Cuối cùng kho báu thật sự nằm ở đâu?", 7),
    ("tên nhân vật", "Fatima là ai?", 4),
]


class BagOfWordsEmbeddings(Embeddings):
    """Embedding giả theo từ (hashing trick, chuẩn hoá L2): gần nhau khi chung từ, đủ để kiểm
    tra đường đi của hybrid retrieval mà không gọi API."""

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for w in re.findall(r"\w+", text.lower()):
            v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def _docs(book: str, passages: Sequence[str]) -> list[Document]:
    return [
        Document(
            page_content=p,
            metadata={
                "book_id": book,
                "source_id": f"https://example.vn/{book}",
                "chunk_index": i,
                "content_hash": hashlib.sha256(p.encode()).hexdigest(),
            },
        )
        for i, p in enumerate(passages)
    ]


@pytest.fixture(scope="module")
def emb() -> Embeddings:
    return BagOfWordsEmbeddings()


@pytest.fixture
def engine(database_url: str, emb: Embeddings) -> Iterator[Engine]:
    vec, rec = make_vector_engine(database_url), make_record_engine(database_url)
    for book, passages in ((BOOK, NHA_GIA_KIM), (OTHER, DE_MEN)):
        index_chunks(
            _docs(book, passages),
            vector_store=make_vector_store(emb, vec),
            record_manager=make_record_manager(rec),
        )
    yield vec
    vec.dispose()
    rec.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(retrieve_top_k=8, rerank_top_n=4, rerank_provider="none")


@pytest.mark.parametrize(("label", "question", "expected"), QUESTIONS)
def test_expected_chunk_in_top4(
    label: str, question: str, expected: int, engine: Engine, emb: Embeddings, settings: Settings
) -> None:
    hits = retrieve(BOOK, question, engine=engine, embeddings=emb, settings=settings)
    assert len(hits) <= 4
    assert expected in [h.metadata["chunk_index"] for h in hits], label


def test_never_returns_other_books(engine: Engine, emb: Embeddings, settings: Settings) -> None:
    # Dế Mèn có đoạn chứa "kho báu", "sa mạc", "Fatima" nhưng không được lẫn vào sách khác.
    for _, question, _ in QUESTIONS:
        hits = retrieve(BOOK, question, engine=engine, embeddings=emb, settings=settings)
        assert hits and {h.metadata["book_id"] for h in hits} == {BOOK}
    hits = retrieve(
        OTHER, "Fatima kho báu sa mạc", engine=engine, embeddings=emb, settings=settings
    )
    assert hits and {h.metadata["book_id"] for h in hits} == {OTHER}


def test_unknown_book_returns_nothing(engine: Engine, emb: Embeddings, settings: Settings) -> None:
    assert retrieve("khong-co", "Fatima", engine=engine, embeddings=emb, settings=settings) == []


def test_requires_book_id_and_ignores_blank_query(
    engine: Engine, emb: Embeddings, settings: Settings
) -> None:
    with pytest.raises(ValueError):
        retrieve("", "Fatima", engine=engine, embeddings=emb, settings=settings)
    assert retrieve(BOOK, "  ", engine=engine, embeddings=emb, settings=settings) == []


def test_query_with_tsquery_operators_is_safe(
    engine: Engine, emb: Embeddings, settings: Settings
) -> None:
    hits = retrieve(BOOK, "Fatima' & !( | :* <->", engine=engine, embeddings=emb, settings=settings)
    assert any(h.metadata["chunk_index"] == 4 for h in hits)


def test_rerank_applied_to_candidates(engine: Engine, emb: Embeddings, settings: Settings) -> None:
    seen: list[tuple[str, int, int]] = []

    class Reverse:
        def rerank(self, query: str, chunks: Sequence[Chunk], top_n: int) -> list[Chunk]:
            seen.append((query, len(chunks), top_n))
            return list(reversed(chunks))[:top_n]

    base = retrieve(BOOK, "kho báu sa mạc", engine=engine, embeddings=emb, settings=settings)
    out = retrieve(
        BOOK, "kho báu sa mạc", engine=engine, embeddings=emb, settings=settings, reranker=Reverse()
    )
    assert seen == [("kho báu sa mạc", 8, 4)]  # rerank nhận 8 ứng viên, trả 4
    assert len(out) == 4 and out[0].id != base[0].id


def test_hybrid_beats_vector_alone_on_rare_name(
    engine: Engine, settings: Settings, emb: Embeddings
) -> None:
    """Embedding không phân biệt được gì thì nhánh full-text vẫn kéo đúng đoạn có tên riêng."""

    class Blind(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0] * DIM for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0] * DIM

    hits = retrieve(BOOK, "Fatima", engine=engine, embeddings=Blind(), settings=settings)
    assert hits[0].metadata["chunk_index"] in (4, 7)  # hai đoạn có "Fatima"
    assert {h.metadata["chunk_index"] for h in hits[:2]} == {4, 7}


def test_user_scope_hides_other_users_chunks(
    database_url: str, emb: Embeddings, settings: Settings, make_user: Callable[[str], str]
) -> None:
    a, b = make_user("ra@example.com"), make_user("rb@example.com")
    rec = make_record_engine(database_url)
    vec_a = make_vector_engine(database_url, a)
    index_chunks(
        [
            Document(
                page_content="Ghi chú riêng của A về Fatima",
                metadata={
                    "book_id": "priv",
                    "user_id": a,
                    "source_id": "note",
                    "chunk_index": 0,
                    "content_hash": "h",
                },
            )
        ],
        vector_store=make_vector_store(emb, vec_a),
        record_manager=make_record_manager(rec, a),
    )
    assert retrieve("priv", "Fatima", engine=vec_a, embeddings=emb, settings=settings)
    vec_b = make_vector_engine(database_url, b)
    assert retrieve("priv", "Fatima", engine=vec_b, embeddings=emb, settings=settings) == []
    for e in (rec, vec_a, vec_b):
        e.dispose()
