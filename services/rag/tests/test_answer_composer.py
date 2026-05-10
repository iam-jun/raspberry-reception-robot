from __future__ import annotations

from app.answer_composer import FALLBACK_MESSAGE, LocalAnswerComposer


def _chunk(text: str, score: float = 0.8) -> dict:
    return {
        "chunk_id": "uit-001",
        "text": text,
        "score": score,
        "metadata": {
            "source_id": "uit_admission_faq",
            "title": "Câu hỏi thường gặp - Tuyển sinh UIT",
            "source_url": "https://tuyensinh.uit.edu.vn/cau-hoi-thuong-gap",
        },
    }


def test_bus_question_returns_only_bus_route_information() -> None:
    raw_context = """
    ## 8. Điều kiện ăn ở, sinh hoạt?
    Ký túc xá ĐHQG nằm trong khu đô thị ĐHQG, cách trường khoảng 1 km.
    Tân sinh viên chuẩn bị 01 Bản sao Giấy báo nhập học, 02 Bản sao CMND.
    - Các tuyến xe bus hằng ngày từ trung tâm thành phố đến ĐHQG-HCM: 8, 10, 19, 30, 33, 50, 52, 53, 99.
    - Các tuyến bus lân cận: 76, 150, 601, 602, 603 (Đến KDL Suối Tiên).
    - Tuyến 6, 601, 602 (Đến ĐH Nông Lâm).
    """

    result = LocalAnswerComposer().compose_answer(
        "Có những tuyến bus nào đến ĐHQG-HCM?",
        [_chunk(raw_context)],
    )

    assert "8" in result["answer"]
    assert "99" in result["answer"]
    assert "76" in result["answer"]
    assert "ký túc xá" not in result["answer"].lower()
    assert "giấy báo nhập học" not in result["answer"].lower()
    assert "##" not in result["answer"]
    assert "###" not in result["answer"]


def test_tuition_question_returns_only_tuition_information() -> None:
    raw_context = """
    ## 7. Học phí
    Học phí dự kiến năm học 2025-2026 đối với hệ Chính quy: 42.000.000 đồng/năm học.
    Ký túc xá cách trường khoảng 1 km.
    Các tuyến xe bus hằng ngày gồm: 8, 10, 19.
    """

    result = LocalAnswerComposer().compose_answer(
        "Học phí chương trình chính quy năm 2025-2026 là bao nhiêu?",
        [_chunk(raw_context)],
    )

    assert "42.000.000" in result["answer"]
    assert "học phí" in result["answer"].lower()
    assert "ký túc xá" not in result["answer"].lower()
    assert "xe bus" not in result["answer"].lower()


def test_unknown_question_returns_fallback_message() -> None:
    raw_context = """
    UIT là trường đại học công lập chuyên ngành Công nghệ Thông tin.
    Mã trường: QSC.
    """

    result = LocalAnswerComposer().compose_answer(
        "UIT có đào tạo ngành Y không?",
        [_chunk(raw_context)],
    )

    assert result["answer"] == FALLBACK_MESSAGE
    assert result["confidence"] == "low"


def test_final_answer_is_not_raw_chunk() -> None:
    raw_context = """
    ## 4. Các chính sách đặc biệt trong đào tạo tại UIT?
    ### b) Học song bằng
    Sinh viên được phép học cùng lúc hai chương trình đào tạo để khi tốt nghiệp nhận hai văn bằng.
    Đây là một dòng không liên quan kéo dài thêm để mô phỏng nội dung thô trong chunk.
    """

    result = LocalAnswerComposer().compose_answer(
        "UIT có cho học song bằng không?",
        [_chunk(raw_context)],
    )

    assert result["answer"] != raw_context
    assert len(result["answer"]) < len(raw_context)
    assert "##" not in result["answer"]

