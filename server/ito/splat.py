"""Ito v1 Splat Batch binary encoding."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable

from server.processors.base import GaussianSplat, ProcessorSplatBatch

MAGIC = b"ITOSPLAT"
VERSION = 1
HEADER = struct.Struct("<8sHHIIH6x")
RECORD = struct.Struct("<ffffffhhhhBBBB")
RECORD_STRIDE = RECORD.size


@dataclass(frozen=True)
class SplatBatchHeader:
    version: int
    flags: int
    sequence: int
    splat_count: int
    record_stride: int


def encode_splat_batch(batch: ProcessorSplatBatch, *, flags: int = 0) -> bytes:
    splats = list(batch.splats)
    payload = bytearray(
        HEADER.pack(MAGIC, VERSION, flags, batch.sequence, len(splats), RECORD_STRIDE)
    )
    for splat in splats:
        payload.extend(_pack_splat(splat))
    return bytes(payload)


def decode_splat_batch_header(payload: bytes) -> SplatBatchHeader:
    magic, version, flags, sequence, splat_count, stride = HEADER.unpack_from(payload)
    if magic != MAGIC:
        raise ValueError("invalid Ito Splat Batch magic")
    if version != VERSION:
        raise ValueError(f"unsupported Ito Splat Batch version: {version}")
    if stride != RECORD_STRIDE:
        raise ValueError(f"unsupported Ito Splat Batch record stride: {stride}")
    expected_size = HEADER.size + splat_count * stride
    if len(payload) != expected_size:
        raise ValueError("Ito Splat Batch payload size does not match header")
    return SplatBatchHeader(version, flags, sequence, splat_count, stride)


def _pack_splat(splat: GaussianSplat) -> bytes:
    x, y, z = splat.position
    sx, sy, sz = splat.scale
    qx, qy, qz, qw = (_quantize_rotation(value) for value in splat.rotation)
    r, g, b, a = (_clamp_u8(value) for value in splat.color)
    return RECORD.pack(x, y, z, sx, sy, sz, qx, qy, qz, qw, r, g, b, a)


def _quantize_rotation(value: float) -> int:
    clamped = max(-1.0, min(1.0, float(value)))
    return int(round(clamped * 32767))


def _clamp_u8(value: int) -> int:
    return max(0, min(255, int(value)))
