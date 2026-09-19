import numpy as np


def encode_rle(mask: np.ndarray) -> str:
    if not np.isin(mask, (0, 1)).all():
        raise ValueError("mask must be binary")
    flat = mask.astype(np.uint8).ravel(order="C")
    edges = np.flatnonzero(np.diff(np.pad(flat, (1, 1)))) + 1
    return " ".join(
        str(number)
        for start, end in zip(edges[::2], edges[1::2], strict=True)
        for number in (int(start), int(end - start))
    )


def decode_rle(value: str, shape: tuple[int, int]) -> np.ndarray:
    if not isinstance(value, str) or value.lower() == "nan":
        raise ValueError("RLE must be a string, with empty predictions encoded as empty string")
    mask = np.zeros(shape[0] * shape[1], dtype=np.uint8)
    if not value.strip():
        return mask.reshape(shape)
    numbers = value.split()
    if len(numbers) % 2:
        raise ValueError("RLE must contain start-length pairs")
    last_end = 0
    for start_text, length_text in zip(numbers[::2], numbers[1::2], strict=True):
        start, length = int(start_text), int(length_text)
        if start <= last_end or start < 1 or length < 1 or start + length - 1 > mask.size:
            raise ValueError("RLE run is overlapping or outside the mask")
        mask[start - 1 : start - 1 + length] = 1
        last_end = start + length - 1
    return mask.reshape(shape)


def roundtrip_check(mask: np.ndarray) -> str:
    rle = encode_rle(mask)
    if not np.array_equal(decode_rle(rle, mask.shape), mask):
        raise ValueError("RLE roundtrip failed")
    return rle


def multiclass_to_binary_rles(mask: np.ndarray, class_ids: tuple[int, ...]) -> dict[int, str]:
    return {
        class_id: roundtrip_check((mask == class_id).astype(np.uint8)) for class_id in class_ids
    }
