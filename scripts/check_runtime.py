"""Check native dependencies before launching the server, away from user data."""
from importlib.metadata import PackageNotFoundError, version
import sys


NATIVE_VERSIONS = {
    "chromadb": "0.5.3",
    "chroma-hnswlib": "0.7.3",
    "numpy": "1.26.4",
    "onnxruntime": "1.19.2",
}


def main() -> int:
    mismatches = []
    for package, expected in NATIVE_VERSIONS.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = "missing"
        if installed != expected:
            mismatches.append(f"{package}: {installed} (expected {expected})")
    if mismatches:
        print("Native dependency mismatch:\n" + "\n".join(mismatches), flush=True)
        print("Run install_and_start.bat to install the tested dependencies.", flush=True)
        return 1

    # A native access violation cannot be caught in Python. The launcher runs
    # this script in a separate process and checks its exit code.
    print("Checking ONNX and HNSW native runtime...", flush=True)
    import onnxruntime  # noqa: F401
    import hnswlib
    import numpy as np

    index = hnswlib.Index(space="l2", dim=1024)
    index.init_index(max_elements=4, ef_construction=100, M=16)
    index.set_num_threads(1)
    vectors = np.zeros((2, 1024), dtype=np.float32)
    vectors[0, 0] = 1
    vectors[1, 1] = 1
    index.add_items(vectors, [0, 1])
    labels, _ = index.knn_query(vectors[:1], k=1)
    if int(labels[0][0]) != 0:
        print("Native vector query failed.", flush=True)
        return 1
    print("Native runtime OK.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
