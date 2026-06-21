from __future__ import annotations

from enum import StrEnum


class BindingStatus(StrEnum):
    PLACEHOLDER = "placeholder"
    ACTIVE = "active"
    INACTIVE = "inactive"

    @classmethod
    def normalize(cls, status: str | None) -> "BindingStatus":
        return cls(status) if status in cls._value2member_map_ else cls.INACTIVE

    @classmethod
    def is_code_usable(cls, status: str | None) -> bool:
        return cls.normalize(status) in {cls.PLACEHOLDER, cls.ACTIVE}
