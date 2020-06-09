from __future__ import annotations

import typing
import sys
from abc import abstractmethod

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol

from src.packages.rescue import Rescue

if typing.TYPE_CHECKING:
    from ..rat import Rat

_DTYPE = typing.TypeVar("_DTYPE")


class ApiConverter(Protocol[_DTYPE]):
    @classmethod
    def to_api(cls, data: _DTYPE) -> typing.Dict:
        ...

    @classmethod
    @abstractmethod
    def from_api(cls, data: typing.Dict) -> _DTYPE:
        ...
