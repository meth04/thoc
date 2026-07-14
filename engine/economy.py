"""Các phép đo kinh tế thuần quan sát, không thay đổi luật engine.

Module tách riêng để tránh việc metric (hộ gia đình, an ninh lương thực, năng suất
đất) len vào logic sản xuất hoặc thị trường. Không hàm nào ở đây được phép chuyển
tài sản, đặt giá, hay rẽ nhánh hành vi.
"""

from __future__ import annotations

from statistics import median

from engine.world import World


def households(w: World) -> list[list[str]]:
    """Trả các hộ sống không trùng lặp, định danh ổn định theo id nhỏ nhất.

    ``World.ho_cua`` đã thể hiện quan hệ gia đình; hàm này chỉ chuẩn hóa để các
    thống kê không đếm một cặp vợ chồng hai lần.
    """
    groups = {
        tuple(sorted(w.ho_cua(aid)))
        for aid, agent in w.agents.items()
        if agent.con_song
    }
    return [list(group) for group in sorted(groups)]


def household_food_need(w: World, members: list[str]) -> float:
    """Nhu cầu thóc một tick của hộ, dùng đúng tham số tiêu dùng hiện hữu."""
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    adult_need = float(w.cfg.get("nhu_cau.nguoi_lon_kg_tick"))
    child_need = float(w.cfg.get("nhu_cau.tre_em_kg_tick"))
    return sum(
        adult_need if w.agents[aid].tuoi_nam >= adult_age else child_need
        for aid in members
    )


def food_equivalence(w: World) -> dict[str, float]:
    """Kg-thóc-equivalent trên một đơn vị thực phẩm đang được scenario cho phép."""
    values = {"thoc": 1.0}
    for crop, spec in w.cfg.get("khong_gian.vu_dong.cay", {}).items():
        if isinstance(spec, dict) and "quy_doi_dinh_duong" in spec:
            values[str(crop)] = float(spec["quy_doi_dinh_duong"])
    return values


def household_grain(w: World, members: list[str]) -> float:
    """Kho thóc riêng (legacy-compatible); dùng food_equivalent cho an ninh thực phẩm."""
    return sum(w.ledger.so_du(aid, "thoc") for aid in members)


def household_food_equivalent(w: World, members: list[str]) -> float:
    """Tồn kho lương thực quy thóc, gồm lúa và cây vụ đông nếu scenario bật."""
    return sum(
        w.ledger.so_du(aid, asset) * factor
        for aid in members
        for asset, factor in food_equivalence(w).items()
    )


def household_snapshot(w: World) -> list[dict[str, float | str]]:
    """Ảnh chụp tồn kho và an ninh lương thực cấp hộ cho metric/analysis.

    Khi ``ho.cu_tru_ben_vung`` bật, mỗi dòng mang thêm ``rid`` (id hộ cư trú BỀN) để metric
    quan sát (poverty streak) bám vào một định danh không gãy khi chủ hộ đổi/chết.
    """
    from engine.household import rid_cua

    rows: list[dict[str, float | str]] = []
    for members in households(w):
        need = household_food_need(w, members)
        grain = household_grain(w, members)
        food_equiv = household_food_equivalent(w, members)
        row: dict[str, float | str] = {
            "head": members[0],
            "members": float(len(members)),
            "grain": grain,
            "food_equivalent": food_equiv,
            "food_need": need,
            "food_security": food_equiv / need if need else 0.0,
        }
        rid = rid_cua(w, members[0])
        if rid is not None:
            row["rid"] = rid
        rows.append(row)
    return rows


def expected_weather_factor(w: World) -> float:
    """Kỳ vọng vô điều kiện của hệ số thời tiết từ chính config scenario."""
    table = w.cfg.get("thoi_gian.thoi_tiet")
    return sum(float(value["p"]) * float(value["he_so"]) for value in table.values())


def expected_parcel_net_output(w: World, parcel_id: str) -> float:
    """Sản lượng thóc kỳ vọng sau giống, trước lao động và tài chính.

    Đây là thước đo vật chất để kiểm tra vốn hóa đất; nó **không** là giá đất, tô
    hay quy tắc hành vi. Không trừ lao động vì mô hình chưa có giá cơ hội lao động
    được nhận diện một cách thực chứng.
    """
    parcel = w.parcels.get(parcel_id)
    if parcel is None or parcel.loai != "ruong":
        return 0.0
    gross = (
        float(w.cfg.get("san_xuat.san_luong_goc_kg"))
        * float(parcel.mau_mo)
        * expected_weather_factor(w)
    )
    return max(0.0, gross - float(w.cfg.get("san_xuat.giong_kg_moi_thua")))


def expected_land_value(w: World, parcel_id: str) -> float:
    """Giá tham chiếu hành vi từ dòng sản lượng kỳ vọng, không phải giá engine.

    Người bán/người mua cần một neo để đặt ask/bid trước giao dịch đầu tiên. Neo này
    là hiện giá của phần sản lượng thuộc chủ đất, với horizon và chiết khấu công khai
    trong config. Sau khi thị trường có lịch sử, neo được pha với giá khớp gần đây và
    điều chỉnh theo năng suất thửa. Chợ vẫn là nơi duy nhất quyết định giá giao dịch.
    """
    cfg = w.cfg.get("hanh_vi.dat_dai")
    output = expected_parcel_net_output(w, parcel_id)
    owner_income = output * float(cfg["ty_le_san_luong_chu_dat"])
    discount = float(cfg["chiet_khau_moi_tick"])
    horizon = int(cfg["ky_han_dinh_gia_tick"])
    intrinsic = sum(owner_income / ((1.0 + discount) ** t) for t in range(1, horizon + 1))
    market = w.gia_tb_4_tick("dat")
    if market is None:
        return intrinsic
    productive_parcels = [
        expected_parcel_net_output(w, p.id) for p in w.parcels.values() if p.loai == "ruong"
    ]
    average = sum(productive_parcels) / len(productive_parcels) if productive_parcels else 0.0
    scaled_market = market * output / average if average > 0 else market
    market_weight = float(cfg["trong_so_gia_thi_truong"])
    return market_weight * scaled_market + (1.0 - market_weight) * intrinsic


def land_price_productivity(w: World, window_ticks: int) -> dict[str, float]:
    """Tổng hợp giao dịch đất gần đây thành price / expected-net-output.

    Tỷ số chỉ được báo khi có giao dịch thật. Như vậy metric không ngầm bịa giá
    thửa đất chưa thanh khoản, và có thể dùng để phát hiện sai lệch E7.
    """
    transactions = [
        item for item in getattr(w, "giao_dich_dat", [])
        if int(item["tick"]) >= w.tick - window_ticks and float(item["expected_net_output"]) > 0
    ]
    ratios = [float(item["price"]) / float(item["expected_net_output"]) for item in transactions]
    return {
        "land_transactions_window": float(len(transactions)),
        "land_price_to_expected_output": float(median(ratios)) if ratios else 0.0,
    }
