"""Kỳ vọng giá chủ quan, có provenance cấu hình và học từ giao dịch thật.

Chợ vẫn là nơi DUY NHẤT quyết định giá khớp. Module này chỉ cho các mind một neo
reservation-value trước giao dịch đầu tiên; không có nhánh engine nào được dùng nó để
ép giá hoặc tự chuyển tài sản.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.world import World


def _spec(w: World, tai_san: str) -> dict:
    cfg = w.cfg.get("hanh_vi.gia_ky_vong")
    assets = cfg.get("tai_san", {})
    raw = assets.get(tai_san, cfg["mac_dinh"])
    return dict(raw)


def _gia_prior(w: World, aid: str, tai_san: str) -> float:
    """Neo riêng của agent, đã seeded khi sinh thế giới; entity dùng neo người điều hành.

    Asset xuất hiện muộn (blueprint hàng mới) không được bịa bằng literal trong code:
    chúng lấy ``mac_dinh`` đã version trong scenario. Không mutate khi đọc để builder
    prompt/tool vẫn thuần đọc.
    """
    agent = w.agents.get(aid)
    if agent is None and aid in w.entities:
        from engine.entities import nguoi_dieu_hanh

        operator = nguoi_dieu_hanh(w, aid)
        agent = w.agents.get(operator) if operator else None
    if agent is not None and tai_san in agent.gia_ky_vong:
        return max(0.0, float(agent.gia_ky_vong[tai_san]))
    return max(0.0, float(_spec(w, tai_san)["trung_vi"]))


def khoi_tao_gia_ky_vong(w: World, aid: str, generator) -> dict[str, float]:
    """Rút prior heterogeneous nhưng tái lập cho một agent mới.

    ``he_so_phan_tan`` là độ lệch tương đối tối đa quanh trung vị và nằm hoàn toàn trong
    config scenario. Agent mới sinh sau này gọi cùng hàm bằng RNG con riêng của tick/id.
    """
    cfg = w.cfg.get("hanh_vi.gia_ky_vong")
    out: dict[str, float] = {}
    for tai_san, raw in sorted(cfg.get("tai_san", {}).items()):
        spec = dict(raw)
        center = float(spec["trung_vi"])
        spread = float(spec.get("he_so_phan_tan", cfg["he_so_phan_tan_mac_dinh"]))
        value = center * (1.0 + float(generator.uniform(-spread, spread)))
        out[str(tai_san)] = round(max(0.0, value), 8)
    return out


def gia_ky_vong(w: World, aid: str, tai_san: str, thanh_toan: str = "thoc") -> float:
    """Giá limit hợp lý của ``tai_san`` bằng đơn vị ``thanh_toan``.

    Ưu tiên quan sát giao dịch thật; chỉ khi chợ chưa có dữ liệu mới dùng prior của chính
    người đặt lệnh. Nhờ vậy `or 12.0`/`or 100.0` trong policy biến mất mà chợ vẫn tự do.
    """
    if tai_san == thanh_toan:
        return 1.0
    if thanh_toan == "thoc":
        observed = w.gia_gan_nhat(tai_san)
        return float(observed) if observed is not None and observed > 0 else _gia_prior(w, aid, tai_san)

    quote = w.gia_gan_nhat(f"{tai_san}/{thanh_toan}")
    if quote is not None and quote > 0:
        return float(quote)
    # Hàng hóa A/B = (thóc/A) / (thóc/B). Không có giá B bằng thóc thì prior B là
    # information set của agent, không phải giá engine.
    gia_a = 1.0 if tai_san == "thoc" else gia_ky_vong(w, aid, tai_san)
    gia_b = 1.0 if thanh_toan == "thoc" else gia_ky_vong(w, aid, thanh_toan)
    return gia_a / gia_b if gia_b > 0 else 0.0


def cap_nhat_gia_ky_vong(w: World) -> None:
    """Cập nhật prior của người sống bằng giá khớp mới nhất trong tick hiện hành.

    Không có giao dịch ⇒ niềm tin giữ nguyên; điều này tránh tạo một "giá engine" ở thị
    trường rỗng. Học cùng một quy tắc ở mọi agent nhưng từ prior riêng, nên dispersion
    chỉ giảm dần qua bằng chứng thị trường thay vì biến mất tức thì.
    """
    cfg = w.cfg.get("hanh_vi.gia_ky_vong")
    alpha = float(cfg["he_so_cap_nhat"])
    observations = {
        tai_san: float(history[-1][1])
        for tai_san, history in w.gia_lich_su.items()
        if history and int(history[-1][0]) == w.tick and "/" not in tai_san
        and float(history[-1][1]) > 0
    }
    if not observations:
        return
    for agent in w.agents.values():
        if not agent.con_song:
            continue
        for tai_san, market_price in observations.items():
            old = _gia_prior(w, agent.id, tai_san)
            agent.gia_ky_vong[tai_san] = round(
                max(0.0, alpha * market_price + (1.0 - alpha) * old), 8
            )
