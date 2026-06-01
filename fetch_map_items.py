import logging

import requests
from sqlalchemy import Float, Integer, String, Text, create_engine, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ======================== 常量 ========================

DB_PATH = "map_items.db"

GET_STATES_URL = "https://api.kurobbs.com/map/core/position/getMapStateSelection"
POSITION_URL_TEMPLATE = "https://web-static.kurobbs.com/mcmap/position/{state_id}/position.json"


# ======================== 数据模型 ========================

class Base(DeclarativeBase):
    pass


class State(Base):
    """地图区域（州/省）"""
    __tablename__ = "state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    locations: Mapped[list["Location"]] = relationship(back_populates="state")


class Country(Base):
    """地图国家/地区"""
    __tablename__ = "country"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    locations: Mapped[list["Location"]] = relationship(back_populates="country")


class Item(Base):
    """地图物品类型"""
    __tablename__ = "item"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    locations: Mapped[list["Location"]] = relationship(back_populates="item")


class Location(Base):
    """物品在地图上的具体位置"""
    __tablename__ = "location"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    item_id: Mapped[str] = mapped_column(String, ForeignKey("item.id"), nullable=False)
    state_id: Mapped[int] = mapped_column(Integer, ForeignKey("state.id"), nullable=False)
    country_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("country.id"), nullable=True)
    floor_id: Mapped[str] = mapped_column(String, default="")
    gravity_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str] = mapped_column(String, default="0")
    online: Mapped[int] = mapped_column(Integer, default=0)
    type_id: Mapped[str | None] = mapped_column(String, nullable=True)
    x: Mapped[float | None] = mapped_column(Float, nullable=True)
    y: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")

    item: Mapped["Item"] = relationship(back_populates="locations")
    state: Mapped["State"] = relationship(back_populates="locations")
    country: Mapped["Country | None"] = relationship(back_populates="locations")


# ======================== API 请求 ========================

def fetch_states() -> dict:
    """获取地图分区及国家列表"""
    resp = requests.get(GET_STATES_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"获取分区失败: {data.get('msg')}")
    return data["data"]


def fetch_positions(state_id: int) -> list:
    """获取指定区域的物品位置数据"""
    url = POSITION_URL_TEMPLATE.format(state_id=state_id)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ======================== 数据持久化 ========================

def _build_location(loc: dict, item_id: str, state_id: int) -> Location:
    """从 API 返回的位置字典构造 Location 对象"""
    return Location(
        id=loc["id"],
        item_id=item_id,
        state_id=state_id,
        country_id=loc.get("countryId"),
        floor_id=loc.get("floorId", ""),
        gravity_type=loc.get("gravityType"),
        level=loc.get("level", "0"),
        online=int(loc.get("online", False)),
        type_id=loc.get("typeId"),
        x=loc.get("x"),
        y=loc.get("y"),
        description=loc.get("description", ""),
    )


def save_states_and_countries(session: Session, states_data: dict):
    """保存区域和国家数据（存在则更新，不存在则插入）"""
    for s in states_data.get("state", []):
        session.merge(State(id=s["id"], name=s["name"]))
    for c in states_data.get("country", []):
        session.merge(Country(id=c["id"], name=c["name"]))
    session.commit()


def save_positions(session: Session, items: list[dict], state_id: int):
    """保存物品及其位置数据（存在则更新，不存在则插入）"""
    for item_data in items:
        item_id = item_data.get("id")
        session.merge(Item(
            id=item_id,
            name=item_data.get("name"),
            icon=item_data.get("icon"),
        ))
        session.flush()

        for loc in item_data.get("location", []):
            session.merge(_build_location(loc, item_id, state_id))
    session.commit()


# ======================== 主流程 ========================

def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.drop_all(engine, tables=[State.__table__, Country.__table__, Item.__table__, Location.__table__])
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        logger.info("正在获取地图分区...")
        states_data = fetch_states()
        save_states_and_countries(session, states_data)

        states = states_data.get("state", [])
        logger.info("共 %d 个区域", len(states))

        for i, state in enumerate(states, 1):
            state_id = state["id"]
            state_name = state["name"]
            logger.info("[%d/%d] 正在获取 %s (id=%d) 的物品...", i, len(states), state_name, state_id)
            try:
                items = fetch_positions(state_id)
                save_positions(session, items, state_id)
                loc_count = sum(len(item.get("location", [])) for item in items)
                logger.info("  -> %d 种物品, %d 个位置", len(items), loc_count)
            except Exception as e:
                logger.error("  -> 获取失败: %s", e)

        item_count = session.query(func.count(Item.id)).scalar()
        loc_count = session.query(func.count(Location.id)).scalar()
        logger.info("完成! 共 %d 种物品, %d 个位置, 已保存到 %s", item_count, loc_count, DB_PATH)


if __name__ == "__main__":
    main()
